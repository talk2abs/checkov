import os
import unittest
from unittest import mock

from checkov.helm.runner import Runner


class TestFindChart(unittest.TestCase):

    def test_find_chart_file(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        test_project_dir = os.path.join(current_dir, 'example_project')
        chart_dirs = Runner.find_chart_directories(None, [os.path.join(test_project_dir, 'chart1', 'Chart.yaml')])
        self.assertEqual(len(chart_dirs), 1)
        self.assertIn(os.path.join(test_project_dir, 'chart1'), chart_dirs)

    def test_find_chart_multiple_files(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        test_project_dir = os.path.join(current_dir, 'example_project')
        chart_dirs = Runner.find_chart_directories(None,
                                                   [
                                                       os.path.join(test_project_dir, 'chart1', 'Chart.yaml'),
                                                       os.path.join(test_project_dir, 'k8s', 'deployment.yaml'),
                                                       os.path.join(test_project_dir, 'charts', 'chart2', 'Chart.yaml')
                                                   ])
        self.assertEqual(len(chart_dirs), 2)
        self.assertIn(os.path.join(test_project_dir, 'chart1'), chart_dirs)
        self.assertIn(os.path.join(test_project_dir, 'charts', 'chart2'), chart_dirs)

    def test_find_chart_no_chart_files(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        test_project_dir = os.path.join(current_dir, 'example_project')
        chart_dirs = Runner.find_chart_directories(None, [os.path.join(test_project_dir, 'k8s', 'deployment.yaml')])
        self.assertEqual(len(chart_dirs), 0)

    def test_find_chart_dir(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        test_project_dir = os.path.join(current_dir, 'example_project')
        chart_dirs = Runner.find_chart_directories(os.path.join(test_project_dir, 'chart1'), None)
        self.assertEqual(len(chart_dirs), 1)
        self.assertIn(os.path.join(test_project_dir, 'chart1'), chart_dirs)

    def test_find_chart_recursive(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        test_project_dir = os.path.join(current_dir, 'example_project')
        chart_dirs = Runner.find_chart_directories(os.path.join(test_project_dir), None)
        self.assertEqual(len(chart_dirs), 2)
        self.assertIn(os.path.join(test_project_dir, 'chart1'), chart_dirs)
        self.assertIn(os.path.join(test_project_dir, 'charts', 'chart2'), chart_dirs)