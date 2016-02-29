#!/usr/bin/python
# encoding: utf-8
#
# Copyright 2013 The Pennsylvania State University.
#
"""
BESImporter.py

Created by Matt Hansen (mah60@psu.edu) on 2013-11-04.

AutoPkg Processor for importing tasks using the BigFix RESTAPI
"""

import besapi

from autopkglib import Processor, ProcessorError

import requests
try:
    requests.packages.urllib3.disable_warnings()
except:
    pass

__all__ = ["BESImporter"]

class BESImporter(Processor):
    """AutoPkg Processor for importing tasks using the BigFix RESTAPI"""
    description = "Generates BigFix XML to install application."
    input_variables = {
        "bes_file": {
            "required": True,
            "description":
                "Path to BES XML file for console import."
        },
        "bes_customsite": {
            "required": True,
            "description":
                "BES console custom site for generated content."
        },
        "BES_ROOTSERVER": {
            "required": True,
            "description":
                "URL to BES root server. e.g https://bes.domain.tld:52311/api"
        },
        "BES_USERNAME": {
            "required": True,
            "description":
                "Console username with write permissions to BES_CUSTOMSITE."
        },
        "BES_PASSWORD": {
            "required": True,
            "description":
                "Console password for BES_USERNAME."
        },
    }
    output_variables = {
        "bes_id": {
            "description":
                "The resulting ID of the BES console import."
        },
        "bes_importer_summary_result": {
            "description": "Description of BigFix import results."
        },
    }
    __doc__ = description


    def main(self):
        """BESImporter Main Method"""
        # Assign BES Console Variables
        bes_file = self.env.get("bes_file")
        bes_title = self.env.get("bes_title")
        bes_customsite = self.env.get("bes_customsite")
        
        BES_USERNAME = self.env.get("BES_USERNAME")
        BES_PASSWORD = self.env.get("BES_PASSWORD")
        BES_ROOTSERVER = self.env.get("BES_ROOTSERVER")

        # BES Console Connection
        B = besapi.BESConnection(BES_USERNAME,
                                BES_PASSWORD,
                                BES_ROOTSERVER,
                                verify=False)

        self.output("Searching: '%s' for %s" % (bes_customsite, bes_title))
        tasks = B.get('tasks/custom/%s' % bes_customsite)

        duplicate_task = False
        for task in tasks().iterchildren():
            if (task.Name == bes_title):
                duplicate_task = True
                
                self.output("Found:[%s] %s - %s    " % (
                    task.ID, task.Name, task.get('LastModified')))

        if not duplicate_task:
            self.output("Importing: '%s' to %s/tasks/custom/%s" %
                        (bes_file, BES_ROOTSERVER, bes_customsite))

            # Upload task
            with open(bes_file, 'r') as bes_file_handle:
                upload_result = B.post('tasks/custom/%s' % bes_customsite, bes_file_handle)
    
            # Read and parse Console return
            self.env['bes_id'] = str(upload_result().Task.ID)
            self.output("Result (%s): [%s] %s - %s    " % (
                upload_result.request.status_code,
                upload_result().Task.ID,
                upload_result().Task.Name,
                upload_result().Task.get('LastModified')))
            
            # Create summary result data    
            self.env["bes_importer_summary_result"] = {
                "summary_text": "The following tasks were imported into BigFix:",
                "report_fields": ["Task ID", "Task Name", "Site"],
                
                "data": {
                    "Task ID": str(upload_result().Task.ID),
                    "Task Name": str(upload_result().Task.Name),
                    "Site": str(bes_customsite),
                }
            }
            
        else:
            self.output("Duplicate, skipping import.")
            self.env['bes_id'] = None

if __name__ == "__main__":
    processor = BESImporter()
    processor.execute_shell()
