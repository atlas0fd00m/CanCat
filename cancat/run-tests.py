import unittest
from cancat.ccp.test_ccp_leader import TestCcpMessageGeneration, TestCcpMessageParsing
from cancat.ccp.test_ccp_follower import TestCcpFollowerMessageParsing, TestCCPFollowerMessageGeneration

testrunner_leader_gen = TestCcpMessageGeneration()
testrunner_leader_gen.runTest()

testrunner_leader_parse = TestCcpMessageParsing()
testrunner_leader_parse.runTest()


testrunner_follower_parse = TestCcpFollowerMessageParsing()
testrunner_follower_parse.runTest()

testrunner_follower_gen = TestCCPFollowerMessageGeneration()
testrunner_follower_gen.runTest()
