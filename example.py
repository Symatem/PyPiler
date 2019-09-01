def foo(a, b):
    c = a + b / 2
    d = c * 0.5
    return d

import PyPiler
print(PyPiler.parse_function(foo))
