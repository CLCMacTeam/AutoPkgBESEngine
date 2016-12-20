#!/usr/bin/python
#
# Copyright 2013 The Pennsylvania State University.
#
"""
AutoPkgBESEngine.py

Created by Matt Hansen (mah60@psu.edu) on 2013-10-08.

AutoPkg Processor for BES (BigFix) XML Tasks and Fixlets
"""
import os
import base64
import hashlib
import getpass
import datetime
import subprocess


from time import gmtime, strftime
from collections import OrderedDict

import requests
from lxml import etree
from FoundationPlist import FoundationPlist
from autopkglib import Processor, ProcessorError, get_autopkg_version


__all__ = ["AutoPkgBESEngine"]
__version__ = '1.4'

QNA = '/usr/local/bin/QnA'

class AutoPkgBESEngine(Processor):
    """
    AutoPkg Processor for BES (BigFix) XML Tasks and Fixlets
    """

    description = "Generates BigFix XML to install application."
    input_variables = {
        "bes_overrideurl": {
            "required": False,
            "description":
                "Custom override for the prefetch url, defaults to %url%."
        },
        "bes_softwareinstaller": {
            "required": False,
            "description":
                "Path to the installer for prefetch, defaults to %pathname%"
        },
        "bes_filename": {
            "required": False,
            "description":
                "Filename for prefetch command, defaults to tail of the URL"
        },
        "bes_prefetch": {
            "required": False,
            "description":
                "Prefetch to prepend to action, usually provided by BESUploader"
        },
        "bes_version": {
            "required": True,
            "description":
                "Version string for relevance, usually provided by Versioner"
        },
        "bes_title": {
            "required": False,
            "description":
                "Task title, defaults to 'Deploy %name% %version%'"
        },
        "bes_description": {
            "required": False,
            "description": (
                "Task description, defaults to "
                "'This task will install %name% %version%'")
        },
        "bes_category": {
            "required": False,
            "description":
                "Appliation category, defaults to 'Software Deployment'"
        },
        "bes_relevance": {
            "required": True,
            "description":
                "Appliation category, defaults to 'Software Deployment'"
        },
        "bes_actions": {
            "required": True,
            "description":
                "A nested dictionary of a single action or multiple actions."
        },
        "bes_ssa": {
            "required": False,
            "description":
                "Add self-service app UI metadata to task, defaults to False."
        },
        "bes_icon": {
            "required": False,
            "description":
                "Base64 encoded icon to add to self-service app UI metadata."
        },
        "bes_additionalmimefields": {
            "required": False,
            "description":
                "A dictionary of additional MIME fields to add to the task."
        }
    }
    output_variables = {
        "bes_file": {
            "description":
                "The file path to the final .bes file."
        },
    }
    __doc__ = description

    def __init__(self, env):
        self.env = env
        self.doc = etree.ElementTree()

    def get_direct_url(self, url):
        """
        Return a direct url for a download link and spoof the User-Agent.
        """

        useragentsplist = ('/Applications/Safari.app'
                           '/Contents/Resources/UserAgents.plist')

        useragent = FoundationPlist.readPlist(useragentsplist)[0]['user-agent']

        headers = {'User-Agent' : useragent.encode('ascii')}
        request = requests.head(url, headers=headers)

        return request.headers.get('location', request.url).encode('ascii')

    def get_prefetch(self, file_path, file_name, url):
        """
        Return a prepared prefetch statement string.
        """

        sha1 = self.get_sha1(file_path)
        sha256 = self.get_sha256(file_path)
        size = self.get_size(file_path)

        return "prefetch %s sha1:%s size:%d %s sha256:%s" % (file_name, sha1,
                                                             size, url, sha256)

    def get_sha1(self, file_path=""):
        if not file_path:
            file_path = self.env.get("bes_softwareinstaller", self.env.get("pathname"))

        return hashlib.sha1(file(file_path).read()).hexdigest()

    def get_sha256(self, file_path=""):
        if not file_path:
            file_path = self.env.get("bes_softwareinstaller", self.env.get("pathname"))

        return hashlib.sha256(file(file_path).read()).hexdigest()

    def get_size(self, file_path=""):
        if not file_path:
            file_path = self.env.get("bes_softwareinstaller", self.env.get("pathname"))

        return os.path.getsize(file_path)

    def get_icon(self, bes_icon):
        r = requests.get(bes_icon)

        b64content = base64.b64encode(r.content)
        #content_type = r.headers['Content-Type']
        content_type = "image/%s" % r.url.split('.')[-1]

        return "data:%s;base64,%s" % (content_type, b64content)

    def new_node(self, element_name, node_text="", element_attributes={}):
        """
        Creates a new generic node of either CDATA or Text.
        Optionally adds attributes. Returns the new element.
        """

        new_element = etree.Element(element_name)

        if node_text:
            if any((character in """<>&'\"""") for character in node_text):
                new_element.text = etree.CDATA(node_text)
            else:
                new_element.text = node_text
        else:
            new_element = etree.Element(element_name)

        if element_attributes:
            for attrib in element_attributes:
                new_element.set(attrib, element_attributes[attrib])

        return new_element

    def new_mime(self, mime_name, mime_value):
        """
        Creates a new MIME element. Returns the new MIME element.
        """

        new_mime_element = etree.Element('MIMEField')

        new_mime_element.append(self.new_node('Name', mime_name))
        new_mime_element.append(self.new_node('Value', mime_value))

        return new_mime_element

    def new_link_description(self, description):
        """
        Creates action link description. Returns the description element.
        """

        new_descr_element = etree.Element('Description')

        new_descr_element.append(self.new_node('PreLink', description[0]))
        new_descr_element.append(self.new_node('Link', description[1]))
        new_descr_element.append(self.new_node('PostLink', description[2]))

        return new_descr_element

    def new_action_settings(self, settings):
        """
        Creates action settings from a dictionary. Returns the settings element.
        """

        new_action_settings_element = etree.Element('Settings')

        for key, value in settings.items():
            new_action_settings_element.append(self.new_node(key, value))

        return new_action_settings_element

    def new_action(self, action_dict, ssa=False):
        """
        Create new action from a dictionary. Returns the new action.
        """
        if not action_dict.get('Description', False):
            action_dict['Description'] = [
                '%s - Click ' % action_dict['ActionNumber'],
                'here',
                ' to take action.']

        if not action_dict.get('SuccessCriteria', False):
            action_dict['SuccessCriteria'] = 'OriginalRelevance'

        new_action_element = self.new_node(action_dict['ActionName'],
                                           None,
                                           {'ID': action_dict['ActionNumber']})

        new_action_element.append(
            self.new_link_description(action_dict['Description']))

        new_action_element.append(
            self.new_node('ActionScript',
                          action_dict['ActionScript'],
                          {'MIMEType': 'application/x-Fixlet-Windows-Shell'}))

        new_action_element.append(
            self.new_node('SuccessCriteria',
                          None,
                          {'Option': action_dict['SuccessCriteria']}))

        if ssa:
            settings = OrderedDict((('ActionUITitle', self.env.get('NAME')),
                                   ('HasEndTime', 'false'),
                                   ('Reapply', 'true'),
                                   ('HasReapplyLimit', 'true'),
                                   ('ReapplyLimit', '5'),
                                   ('HasReapplyInterval', 'false'),
                                   ('IsOffer', 'true'),
                                   ('OfferCategory', self.env.get('OfferCategory', '')),
                                   ('OfferDescriptionHTML', self.env.get('OfferDescriptionHTML', '')),
                                  ))
            new_action_element.append(self.new_action_settings(settings))

        return new_action_element

    def validate_relevance(self, relevance):
        """
        Validate a line of relevance by parsing the output of the QnA utility.
        """
        try:
            proc = subprocess.Popen(QNA,
                                    bufsize=-1,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            out, err = proc.communicate(relevance)

            output = {}
            for line in out.strip().split('\n'):
                output[line.split(':')[0].strip()] = line.split(':')[1].strip()

            if output.get('E', None):
                self.output("Relevance Error: {%s} -- %s" %
                            (relevance,
                             output.get('E')))
            return True
        except Exception, error:
            self.output("Relevance Error: (%s) -- %s" % (QNA, error))
            return True

    def main(self):
        """
        Create a BES software distribution task.
        """

        # Assign Application Variables
        url = self.get_direct_url(
            self.env.get("bes_overrideurl",
                         self.env.get("url")))

        user = getpass.getuser()
        bes_size = self.get_size()
        gmtime_now = strftime("%a, %d %b %Y %X +0000", gmtime())

        bes_displayname = self.env.get("NAME")

        bes_version = self.env.get("bes_version")

        bes_title = self.env.get("bes_title",
                                 "Deploy %s %s" %
                                 (bes_displayname, bes_version))

        bes_category = self.env.get("bes_category", 'Software Deployment')

        bes_relevance = self.env.get("bes_relevance")

        bes_filename = self.env.get("bes_filename", url.split('/')[-1])
        bes_filename = bes_filename.strip().replace(' ', '_')

        bes_prefetch = self.env.get("bes_prefetch",
                                    self.get_prefetch(None,
                                                      bes_filename,
                                                      url))

        bes_description = self.env.get("bes_description",
                                       'This task will deploy %s %s.<BR><BR>'
                                       'This task is applicable on Mac OS X' %
                                       (bes_displayname, bes_version))

        bes_actions = self.env.get("bes_actions",
                                   {1:{'ActionName': 'DefaultAction',
                                       'ActionNumber': 'Action1',
                                       'ActionScript': """"""}})

        bes_preactionscript = self.env.get("bes_preactionscript", "")
        bes_postactionscript = self.env.get("bes_postactionscript", "")

        bes_ssa = self.env.get("bes_ssa", "False")
        bes_ssaaction = self.env.get("bes_ssaaction", None)
        bes_icon = self.env.get("bes_icon", False)

        bes_additionalmimefields = self.env.get("bes_additionalmimefields", False)

        # Prepend prefetch line to action script for all actions
        # Prepend and append pre and post actionscript additions
        for action in bes_actions:
            bes_actions[action]['ActionScript'] = ("%s\n%s%s\n%s" % (
                bes_preactionscript,
                bes_prefetch,
                bes_actions[action]['ActionScript'],
                bes_postactionscript
            )).strip()

        # Additional Metadata for Task
        details = OrderedDict((
            ('Category', bes_category),
            ('DownloadSize',
             str(os.path.getsize(self.env.get(
                 "bes_softwareinstaller", self.env.get("pathname"))))),
            ('Source', "%s v%s (%s)" % (os.path.basename(__file__),
                                        __version__, str(get_autopkg_version()))),
            ('SourceID', user),
            ('SourceReleaseDate', str(datetime.datetime.now())[:10]),
            ('SourceSeverity', ""),
            ('CVENames', ""),
            ('SANSID', ""),
        ))

        # Start Building BES XML
        self.output("Building 'Deploy %s %s.bes'" %
                    (bes_displayname, bes_version))

        root_schema = {
            "{http://www.w3.org/2001/XMLSchema-instance}" +
            "noNamespaceSchemaLocation": 'BES.xsd'
        }

        root = self.new_node('BES', None, root_schema)
        self.doc._setroot(root)

        # Create Top Level 'Task' Tag
        node = self.new_node('Task', None)
        root.append(node)

        # Append Title and Description
        node.append(self.new_node('Title', bes_title))
        node.append(self.new_node('Description', bes_description))

        # Append Relevance
        for line in bes_relevance:
            if os.path.isfile(QNA):
                self.validate_relevance(line)

            node.append(self.new_node('Relevance', line))

        # Append Details Dictionary
        for key, value in details.items():
            node.append(self.new_node(key, value))

        # Add Self-Service UI Data, If Specified
        if bes_ssa in ['True', 'true']:
            if bes_icon:
                bes_b64icon = self.get_icon(bes_icon)
                node.append(self.new_mime('action-ui-metadata',
                                          ("{\"version\": \"%s\","
                                           "\"size\": \"%s\","
                                           "\"icon\": \"%s\"}") % (bes_version,
                                                                   bes_size,
                                                                   bes_b64icon)))
            else:
                node.append(self.new_mime('action-ui-metadata',
                                          '{"version": "%s", "size": "%s"}' % (bes_version,
                                                                               bes_size)))

        # Append MIME Source Data
        node.append(self.new_mime('x-fixlet-source',
                                  os.path.basename(__file__)))

        # Add Additional MIME Fields
        if bes_additionalmimefields:
            for name, value in bes_additionalmimefields.iteritems():
                node.append(self.new_mime(name, value))

        # Add Modification Time
        node.append(
            self.new_mime('x-fixlet-modification-time', gmtime_now))

        node.append(self.new_node('Domain', 'BESC'))

        # Append Default Action
        bes_ssaaction_copy = None
        for action in sorted(bes_actions.iterkeys()):

            if bes_actions[action].get('ActionName', None) == bes_ssaaction:
                bes_ssaaction_copy = bes_actions[action]

            if bes_actions[action].get('ActionName', None) == 'DefaultAction':
                node.append(self.new_action(bes_actions[action]))
                bes_actions.pop(action, None)

        # Append Actions
        for action in sorted(bes_actions.iterkeys()):
            node.append(self.new_action(bes_actions[action]))

        # Append SSA Action
        if bes_ssaaction and bes_ssaaction_copy:
                bes_ssaaction_copy['Description'] = ['',
                                                     'Make available',
                                                     ' in Self Service']
                bes_ssaaction_copy['ActionNumber'] = 'Action10'
                bes_ssaaction_copy['ActionName'] = 'Action'

                node.append(self.new_action(bes_ssaaction_copy, ssa=True))

        # Write Final BES File to Disk
        bes_file = "%s/Deploy %s %s.bes" % (self.env.get("RECIPE_CACHE_DIR"),
                                            bes_displayname, bes_version)

        self.doc.write(bes_file, encoding="UTF-8", xml_declaration=True)

        self.env['bes_file'] = bes_file
        self.output("Output BES File: '%s'" % self.env.get("bes_file"))

if __name__ == "__main__":
    processor = AutoPkgBESEngine()
    processor.execute_shell()
