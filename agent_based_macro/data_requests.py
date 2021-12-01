"""
data_requests.py

This file generates the ActionDataRequestHolder class. As the name suggests, it holds the information for a data request
for an action.

The class ensures that all required parameters are filled in when the request is created.

It also has the advantage of creating a centralised repository of all data requests, so that developers  can see
what is available without wandering through the source code.

Why do this? Without this class, we only know if required parameters are missing only when the data request is
processed. Since we are event driven, this will only happen in unrelated code after an unknown processing delay.
By validating that the inputs exist up front, code that generates a bad data query will immediately crash.


Copyright 2021 Brian Romanchuk

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""


class ActionDataParameterError(ValueError):
    pass


class ActionDataRequestHolder(object):
    # Static member holding the registered queries.
    GRequired = {}

    def __init__(self, data_dict=None):
        if data_dict is None:
            self.DataDict = {}
            return
        if type(data_dict) is dict:
            self.DataDict = data_dict
        else:
            # Assume it is another ActionDataRequestHolder
            try:
                self.DataDict = data_dict.DataDict
            except:
                raise ValueError('Must pass a dict or ActionDataRequestHolder to ActionDataRequestHolder to constructor')
        self.assert_valid()

    def assert_valid(self):
        for k in self.DataDict:
            self.assert_key_valid(k)

    def assert_key_valid(self, kkey):
        info = self.DataDict[kkey]
        if 'request' not in info:
            raise ActionDataParameterError('All Action data requests must include a "request" parameter')
        if info['request'] not in ActionDataRequestHolder.GRequired:
            raise ActionDataParameterError(f'Action data type "{info["request"]}" is not registered')
        for param in ActionDataRequestHolder.GRequired[info["request"]]:
            if param not in info:
                raise ActionDataParameterError(f'Missing parameter {param} for Action data request {kkey}')

    def add_request(self, kkey, request):
        self.DataDict[kkey] = request
        self.assert_key_valid(kkey)


def register_query(query, required, docstring=''):
    """
    Utility function to register a data request to the global registry

    For now, not dealing with the doctsring
    :param query: str
    :param required: tuple
    :param docstring: str
    :return:
    """
    ActionDataRequestHolder.GRequired[query] = required


# Global list of requests. More can be registered elsewhere.
info = (
    ('Productivity', ('commodity',), 'Get the productivity associated for a commodity'),
    ('JG_Wage', tuple(), 'Get the JobGuarantee wage at the Agent''s location'),
    ('CommodityID', ('commodity',), 'Get the GID of a commodity by name'),
)

for q, r, d in info:
    register_query(q, r, d)