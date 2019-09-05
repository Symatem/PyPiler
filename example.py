def foo(a, b):
    c = a and not b
    d = bar(x=a, y=c)
    return d

import pypiler
compile_unit = pypiler.CompileUnit(foo)
print(compile_unit.parse_function_definition(compile_unit.ast.root_node.children[0]))
