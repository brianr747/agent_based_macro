"""
data_requests.py

This file generates the ActionDataRequestHolder class. As the name suggests, it holds the information for a data request
for an callback.

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

from agent_based_macro.utils import KwargManager

class ActionDataParameterError(ValueError):
    pass


class ActionDataRequestHolder(KwargManager):
    GRequired = {}
    GKey = 'request'
    GDocstrings = {}
    GHandler = {}
    ErrorType = ActionDataParameterError



