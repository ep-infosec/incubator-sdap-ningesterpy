# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import inspect
import re

import sdap.processors


class BadChainException(Exception):
    pass


class ProcessorNotFound(Exception):
    def __init__(self, missing_processor, *args):
        message = "Processor %s is not defined in INSTALLED_PROCESSORS. See processors/__init__.py" % missing_processor

        self.missing_processor = missing_processor
        super().__init__(message, *args)


class MissingProcessorArguments(Exception):
    def __init__(self, processor, missing_processor_args, *args):
        message = "%s is missing required arguments: %s" % (processor, missing_processor_args)

        self.processor = processor
        self.missing_processor_args = missing_processor_args
        super().__init__(message, *args)


class ProcessorChain(sdap.processors.Processor):
    def __init__(self, processor_list, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.processors = []
        # Attempt to construct the needed processors
        for processor in processor_list:
            try:
                processor_constructor = sdap.processors.INSTALLED_PROCESSORS[processor['name']]
            except KeyError as e:
                raise ProcessorNotFound(processor['name']) from e

            processor_config = dict(**processor['config'])

            missing_args = []
            for arg in inspect.signature(processor_constructor).parameters.keys():
                if arg in ['args', 'kwargs']:
                    continue
                if arg not in processor_config:
                    missing_args.append(arg)

            # Need to check for list type args
            list_pattern = re.compile('\.\d+$')
            list_args = [k for k in processor_config if list_pattern.search(k)]
            if list_args:
                import itertools
                grouped = itertools.groupby(list_args, key=lambda k: k.split('.')[0])
                for group, grouped_args in grouped:
                    for list_arg in grouped_args:
                        key, idx = list_arg.split('.')
                        if group not in processor_config:
                            processor_config[group] = []

                        processor_config[group].insert(int(idx), processor_config[list_arg])
                        del(processor_config[list_arg])

            # Check if the list args satisfied the
            missing_args = list(filter(lambda a: a not in processor_config.keys(), missing_args))
            if missing_args:
                raise MissingProcessorArguments(processor['name'], missing_args)

            if 'config' in processor.keys():
                processor_instance = processor_constructor(**processor_config)
            else:
                processor_instance = processor_constructor()

            self.processors.append(processor_instance)

    def process(self, input_data):

        def recursive_processing_chain(gen_index, message):

            next_gen = self.processors[gen_index + 1].process(message)
            for next_message in next_gen:
                if gen_index + 1 == len(self.processors) - 1:
                    yield next_message
                else:
                    for result in recursive_processing_chain(gen_index + 1, next_message):
                        yield result

        return recursive_processing_chain(-1, input_data)
