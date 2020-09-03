import io
import logging
import operator
import os
import subprocess
import tempfile
from functools import reduce

from checkov.common.output.record import Record
from checkov.common.output.report import Report
from checkov.common.runners.base_runner import BaseRunner, filter_ignored_directories
from checkov.kubernetes.runner import Runner as k8_runner
from checkov.helm.registry import registry
from checkov.runner_filter import RunnerFilter

K8_POSSIBLE_ENDINGS = [".yaml", ".yml", ".json"]


class Runner(BaseRunner):
    check_type = "helm"

    @staticmethod
    def find_chart_directories(root_folder, files):
        chart_directories = []
        if files:
            logging.debug('Running with --file argument; checking for Helm Chart.yaml files')
            for file in files:
                if os.path.basename(file) == 'Chart.yaml':
                    chart_directories.append(os.path.dirname(file))

        if root_folder:
            for root, d_names, f_names in os.walk(root_folder):
                filter_ignored_directories(d_names)
                if 'Chart.yaml' in f_names:
                    chart_directories.append(root)

        return chart_directories

    def run(self, root_folder, external_checks_dir=None, files=None, runner_filter=RunnerFilter()):
        report = Report(self.check_type)
        definitions = {}
        definitions_raw = {}
        parsing_errors = {}
        files_list = []
        if external_checks_dir:
            for directory in external_checks_dir:
                registry.load_external_checks(directory, runner_filter)

        chart_directories = self.find_chart_directories(root_folder, files)

        report = Report(self.check_type)

        for chart_dir in chart_directories:
            chart_name = os.path.basename(chart_dir)
            helm_command = 'helm2'
            with tempfile.TemporaryDirectory() as target_dir:
                proc = subprocess.Popen([helm_command, 'install', '--debug', '--dry-run', chart_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                o, e = proc.communicate()

                if e:
                    raise Exception('An error occurred: ' + str(e, 'utf-8'))

                output = str(o, 'utf-8')
                reader = io.StringIO(output)
                cur_source_file = None
                cur_writer = None
                last_line_dashes = False
                line_num = 1
                for s in reader:
                    s = s.rstrip()
                    if s == '---':
                        last_line_dashes = True
                        continue

                    if last_line_dashes:
                        # The next line should contain a "Source" comment saying the name of the file it came from
                        # So we will close the old file, open a new file, and write the dashes from last iteration plus this line

                        if not s.startswith('# Source: '):
                            raise Exception(f'Line {line_num}: Expected line to start with # Source: {s}')
                        source = s[10:]
                        if source != cur_source_file:
                            if cur_writer:
                                cur_writer.close()
                            file_path = os.path.join(target_dir, source)
                            parent = os.path.dirname(file_path)
                            os.makedirs(parent, exist_ok=True)
                            cur_source_file = source
                            cur_writer = open(os.path.join(target_dir, source), 'a')
                        cur_writer.write('---' + os.linesep)
                        cur_writer.write(s + os.linesep)

                        last_line_dashes = False
                    else:
                        if s.startswith('# Source: '):
                            raise Exception(f'Line {line_num}: Unexpected line starting with # Source: {s}')

                        if not cur_writer:
                            continue
                        else:
                            cur_writer.write(s + os.linesep)

                    line_num += 1

                if cur_writer:
                    cur_writer.close()

                k8s_runner = k8_runner()
                chart_results = k8s_runner.run(target_dir, external_checks_dir=external_checks_dir, runner_filter=runner_filter)

                report.failed_checks += chart_results.failed_checks
                report.passed_checks += chart_results.passed_checks
                report.parsing_errors += chart_results.parsing_errors
                report.skipped_checks += chart_results.parsing_errors

        return report


    def _search_deep_keys(self, search_text, k8n_dict, path):
        """Search deep for keys and get their values"""
        keys = []
        if isinstance(k8n_dict, dict):
            for key in k8n_dict:
                pathprop = path[:]
                pathprop.append(key)
                if key == search_text:
                    pathprop.append(k8n_dict[key])
                    keys.append(pathprop)
                    # pop the last element off for nesting of found elements for
                    # dict and list checks
                    pathprop = pathprop[:-1]
                if isinstance(k8n_dict[key], dict):
                    keys.extend(self._search_deep_keys(search_text, k8n_dict[key], pathprop))
                elif isinstance(k8n_dict[key], list):
                    for index, item in enumerate(k8n_dict[key]):
                        pathproparr = pathprop[:]
                        pathproparr.append(index)
                        keys.extend(self._search_deep_keys(search_text, item, pathproparr))
        elif isinstance(k8n_dict, list):
            for index, item in enumerate(k8n_dict):
                pathprop = path[:]
                pathprop.append(index)
                keys.extend(self._search_deep_keys(search_text, item, pathprop))

        return keys

def get_skipped_checks(entity_conf):
    skipped = []
    metadata = {}
    if not isinstance(entity_conf,dict):
        return skipped
    if entity_conf["kind"] == "containers" or entity_conf["kind"] == "initContainers":
        metadata = entity_conf["parent_metadata"]
    else:
        if "metadata" in entity_conf.keys():
            metadata = entity_conf["metadata"]
    if "annotations" in metadata.keys() and metadata["annotations"] is not None:
        for key in metadata["annotations"].keys():
            skipped_item = {}
            if "checkov.io/skip" in key or "bridgecrew.io/skip" in key:
                if "CKV_K8S" in metadata["annotations"][key]:
                    if "=" in metadata["annotations"][key]:
                        (skipped_item["id"], skipped_item["suppress_comment"]) = metadata["annotations"][key].split("=")
                    else:
                        skipped_item["id"] = metadata["annotations"][key]
                        skipped_item["suppress_comment"] = "No comment provided"
                    skipped.append(skipped_item)
                else:
                    logging.debug("Parse of Annotation Failed for {}: {}".format(metadata["annotations"][key], entity_conf, indent=2))
                    continue
    return skipped

def _get_from_dict(data_dict, map_list):
    return reduce(operator.getitem, map_list, data_dict)


def _set_in_dict(data_dict, map_list, value):
    _get_from_dict(data_dict, map_list[:-1])[map_list[-1]] = value


def find_lines(node, kv):
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        for i in node:
            for x in find_lines(i, kv):
                yield x
    elif isinstance(node, dict):
        if kv in node:
            yield node[kv]
        for j in node.values():
            for x in find_lines(j, kv):
                yield x


