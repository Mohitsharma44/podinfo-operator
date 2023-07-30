import unittest
import time
import unittest.case
import os
import urllib3
from kubernetes.client.configuration import Configuration
from kubernetes.config import kube_config

RED = "\033[1;31m"
GREEN = "\033[1;32m"
NC = "\033[0m"


class PrettyPrintTestResult(unittest.TextTestResult):
    """
    Overriding TextTestResult class to show progress of current test case vs the total number of test cases
    along with pretty formatting of test results
    """

    def __init__(self, stream, descriptions, verbosity):
        self.test_number = 0
        self.test_case_count = 0
        return super(PrettyPrintTestResult, self).__init__(
            stream, descriptions, verbosity
        )

    def startTest(self, test):
        self.startTime = time.time()
        self.test_number += 1
        super().startTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        elapsed = time.time() - self.startTime
        print(
            f"[{self.test_number:02}/{self.test_case_count:02}] {GREEN}✅ {test._testMethodName} took {elapsed:.5f} seconds. {NC}"
        )

    def addFailure(self, test, err):
        super().addFailure(test, err)
        elapsed = time.time() - self.startTime
        print(
            f"[{self.test_number:02}/{self.test_case_count:02}] {RED}❌ {test._testMethodName} took {elapsed:.5f} seconds. {NC}"
        )

    def addError(self, test, err):
        super().addError(test, err)
        elapsed = time.time() - self.startTime
        print(
            f"[{self.test_number:02}/{self.test_case_count:02}] {RED}❌ {test._testMethodName} took {elapsed:.5f} seconds. {NC}"
        )


class PrettyPrintTextTestRunner(unittest.TextTestRunner):
    resultclass = PrettyPrintTestResult

    def run(self, test):
        self.test_case_count = test.countTestCases()
        return super(PrettyPrintTextTestRunner, self).run(test)

    def _makeResult(self):
        result = super(PrettyPrintTextTestRunner, self)._makeResult()
        result.test_case_count = self.test_case_count
        return result

