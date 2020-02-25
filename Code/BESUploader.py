#!/usr/local/autopkg/python
# encoding: utf-8
#
# Copyright 2013 The Pennsylvania State University.
#
"""
BESUploader.py

Created by Matt Hansen (mah60@psu.edu) on 2013-11-06.

AutoPkg Processor for uploading files using the BigFix REST API

Updated by Rusty Myers (rzm102@psu.edu) on 2020-02-21.

Adding support for python3

"""
from __future__ import absolute_import

import os, ssl
import urllib
import base64
import sys
from xml.dom import minidom

from autopkglib import Processor, ProcessorError

__all__ = ["BESUploader"]

class BESUploader(Processor):
    """AutoPkg Processor for uploading files using the BigFix REST API"""
    description = "Uploads a file to the BES Console. Requires Master Operator."
    input_variables = {
        "bes_uploadpath": {
            "required": True,
            "description":
                "Path to the file to import into the console."
        },
        "BES_ROOTSERVER": {
            "required": True,
            "description":
                "URL to BES root server. e.g https://bes.domain.tld:52311/api"
        },
        "BES_USERNAME": {
            "required": True,
            "description":
                "BES console username with upload permissions."
        },
        "BES_PASSWORD": {
            "required": True,
            "description":
                "BES console password for bes_username."
        },
        "bes_filename": {
            "required": False,
            "description":
                "Filename to use in prefetch statement. Defaults to /$sha1/$filename"
        },
        "output_var_name": {
            "required": False,
            "description":
                "Output variable name. Defaults to 'bes_prefetch'"
        }
    }
    output_variables = {
        "bes_uploadname": {
            "description":
                "The resulting name of the BES console upload."
        },
        "bes_uploadurl": {
            "description":
                "The resulting url of the BES console upload."
        },
        "bes_uploadsha1": {
            "description":
                "The resulting sha1 of the BES console upload."
        },
        "bes_uploadsha256": {
            "description":
                "The resulting sha256 of the BES console upload."
        },
        "bes_uploadsize": {
            "description":
                "The resulting size of the BES console upload."
        },
        "bes_prefetch": {
            "description":
                "The compiled prefetch command for the uploaded file."
        },
    }
    __doc__ = description

    def send_api_request(self, api_url, auth_string, bes_file=None):
        """Send generic BES API request"""
        # self.output("Sending BES API Request")
        request = urllib.request(api_url)

        request.add_header("Authorization", "Basic %s" % auth_string)
        request.add_header("Content-Type", "application/xml")

        # Read bes_file contents and add to request
        if bes_file:
            bes_data = open(bes_file).read()
            request.data(bes_data)
            request.add_header("Content-Disposition",
                               'attachment; filename="%s"' %
                               os.path.basename(bes_file))

        # Request POST to Console API
        try:
            # self.output(request.get_full_url())
            # self.output(request.get_method())
            # self.output(request)
            return urllib.request.urlopen(request)


        except urllib.error.HTTPError as error:
            self.output("HTTPError: [%s] %s" % (error.code, error.read()))
            sys.exit(1)
        except urllib.error.URLError as error:
            self.output("URLError: %s" % (error.args))
            sys.exit(1)

    def main(self):
        """BESUploader Main Method"""
        
        # Disable ssl warnings
        if (not os.environ.get('PYTHONHTTPSVERIFY', '') and
            getattr(ssl, '_create_unverified_context', None)): 
            ssl._create_default_https_context = ssl._create_unverified_context
            
        # Assign Console Variables
        bes_uploadpath = self.env.get("bes_uploadpath")
        BES_ROOTSERVER = self.env.get("BES_ROOTSERVER").encode('ascii')
        BES_USERNAME = self.env.get("BES_USERNAME")
        BES_PASSWORD = self.env.get("BES_PASSWORD")

        self.output("Uploading: %s to %s" % (bes_uploadpath,
                                             BES_ROOTSERVER + '/api/upload'))

        # Console Connection Strings
        auth_string = base64.encodestring('%s:%s' %
                                          (BES_USERNAME, BES_PASSWORD)).strip()
        # Send Request
        upload_request = self.send_api_request(BES_ROOTSERVER + "/api/upload",
                                               auth_string, bes_uploadpath)

        #Read and Parse Console Return
        result_dom = minidom.parseString(upload_request.read())
        result_upload = result_dom.getElementsByTagName('FileUpload') or []
        result_name = result_upload[-1].getElementsByTagName('Name')
        result_url = result_upload[-1].getElementsByTagName('URL')
        result_size = result_upload[-1].getElementsByTagName('Size')
        result_sha1 = result_upload[-1].getElementsByTagName('SHA1')
        result_sha256 = result_upload[-1].getElementsByTagName('SHA256')
        # print entire output
        # self.output(result_dom.toxml())
        # Set Output Variables
        # Use bes_filename input or the name result_name
        bes_filename = self.env.get("bes_filename", result_name[-1].firstChild.nodeValue)
        
        self.env['bes_uploadname'] = result_name[-1].firstChild.nodeValue
        self.env['bes_uploadurl'] = result_url[-1].firstChild.nodeValue
        self.env['bes_uploadsize'] = result_size[-1].firstChild.nodeValue
        self.env['bes_uploadsha1'] = result_sha1[-1].firstChild.nodeValue
        self.env['bes_uploadsha256'] = result_sha256[-1].firstChild.nodeValue

        self.env['bes_prefetch'] = (
            "prefetch %s sha1:%s size:%s %s sha256:%s" % (
                bes_filename,
                self.env.get("bes_uploadsha1"),
                self.env.get("bes_uploadsize"),
                self.env.get("bes_uploadurl"),
                self.env.get("bes_uploadsha256"),
            )
        )
        
        output_var_name = self.env.get("output_var_name", 
                                       "bes_prefetch")

        self.env[output_var_name] = (
            "prefetch %s sha1:%s size:%s %s %s" % (
                bes_filename,
                self.env.get("bes_uploadsha1"),
                self.env.get("bes_uploadsize"),
                self.env.get("bes_uploadurl"),
                self.env.get("bes_uploadsha256"),
            )
        )
        
        self.output("%s = %s" %
                    (output_var_name,
                     self.env.get(output_var_name)))

if __name__ == "__main__":
    processor = BESUploader()
    processor.execute_shell()
