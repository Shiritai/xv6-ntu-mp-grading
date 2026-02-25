from gradelib import *
import re

r = Runner()

@test(10, "example test case 1")
def test_example_1():
    r.run_qemu(shell_script(["echo hello world"]))
    r.match("hello world")

@test(10, "example test case 2")
def test_example_2():
    r.run_qemu(shell_script(["ls"]))
    r.match("README")
