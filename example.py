def foo(a, b):
    c = a and not b
    d = bar(x=a, y=c)
    return d

import pypiler
print(pypiler.parse_function(foo))
