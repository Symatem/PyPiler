import os
import sys
import inspect
from tree_sitter import Language, Parser

tree_sitter_python_file = os.path.join(os.path.dirname(inspect.getfile(sys.modules[__name__])), 'tree-sitter-python.so')
if not os.path.isfile(tree_sitter_python_file):
    os.system('git clone --depth 1 https://github.com/tree-sitter/tree-sitter-python')
    Language.build_library(tree_sitter_python_file, ['tree-sitter-python'])
    os.system('rm -rf tree-sitter-python')
PY_LANGUAGE = Language(tree_sitter_python_file, 'python')
parser = Parser()
parser.set_language(PY_LANGUAGE)

operator_registry = {}
def get_or_create_operator(identifier):
    if identifier in operator_registry:
        return operator_registry[identifier]
    return Operator(identifier)

class Operator:
    def __init__(self, identifier):
        operator_registry[identifier] = self
        self.operations = {}
        self.self_operation = Operation(self, identifier)
        self.carriers = {}
        self.identifier = identifier

    def __repr__(self):
        return 'Operator<id="{}",\n\tinputs={},\n\toutputs={},\n\toperations=[{}\n\t],\n\tcarriers=[{}\n\t]\n>'.format(
            self.identifier, self.get_input_operands(), self.get_output_operands(),
            ''.join(map(lambda x: '\n\t\t{}'.format(x), self.operations.values())),
            ''.join(map(lambda x: '\n\t\t{}'.format(x), self.carriers.values()))
        )

    def get_input_operands(self):
        return list(map(lambda x: x.operand, self.self_operation.output_bindings.values()))

    def get_output_operands(self):
        return list(map(lambda x: x.operand, self.self_operation.input_bindings.values()))

class Operation:
    def __init__(self, operator, identifier):
        operator.operations[identifier] = self
        self.operator = operator
        self.identifier = identifier
        self.input_bindings = {}
        self.output_bindings = {}

    def __repr__(self):
        return 'Operation<id="{}", in={}, out={}>'.format(self.identifier, self.input_bindings, self.output_bindings)

class CarrierBinding:
    def __init__(self, carrier, operation, operand, type):
        self.carrier = carrier
        self.operation = operation
        self.operand = operand
        if type == 'input':
            carrier.destination_bindings.append(self)
            operation.input_bindings[carrier.identifier] = self
        elif type == 'output':
            carrier.source_binding = self
            operation.output_bindings[carrier.identifier] = self

    def __repr__(self):
        return 'CarrierBinding<"{}" of "{}">'.format(self.operand, self.operation.identifier)

class CarrierTuft:
    def __init__(self, operator, identifier):
        operator.carriers[identifier] = self
        self.operator = operator
        self.identifier = identifier
        self.source_binding = None
        self.destination_bindings = []

    def __repr__(self):
        return 'CarrierTuft<id="{}", src={}, dst={}>'.format(self.identifier, self.source_binding, self.destination_bindings)

def constant_to_carrier(operator, value):
    identifier = 'OpConst<{}>'.format(value.identifier) if isinstance(value, Operator) else 'Literal<{}>'.format(value)
    if identifier in operator.carriers:
        return operator.carriers[identifier]
    operation = Operation(operator, identifier)
    operation.value = value
    carrier = CarrierTuft(operator, identifier)
    CarrierBinding(carrier, operation, 'output', 'output')
    return carrier

def parse_function(func):
    source_code = inspect.getsource(func)
    def node_source_code(node):
        return source_code[node.start_byte:node.end_byte]
    def node_to_identifier(node):
        return '({}) {}:{}'.format(node_source_code(node), node.start_point[0]+1, node.start_point[1]+1)
    def parse_expression(operator, node, output_carrier_identifier=None):
        while node.type == 'parenthesized_expression':
            node = node.children[1]
        if node.type == 'integer' or node.type == 'float' or node.type == 'true' or node.type == 'false' or node.type == 'none' or node.type == 'string':
            return constant_to_carrier(operator, node_source_code(node))
        elif node.type == 'identifier':
            return operator.carriers[node_source_code(node)]
        elif node.type == 'call' or node.type == 'unary_operator' or node.type == 'not_operator' or node.type == 'binary_operator' or node.type == 'boolean_operator' or node.type == 'comparison_operator':
            operation = Operation(operator, node_to_identifier(node))
            operator_to_apply = node.children[0]
            if node.type == 'call':
                for argument in node.children[1].children:
                    if argument.type == 'keyword_argument':
                        CarrierBinding(parse_expression(operator, argument.children[2]), operation, node_source_code(argument.children[0]), 'input')
            elif node.type == 'unary_operator' or node.type == 'not_operator':
                CarrierBinding(parse_expression(operator, node.children[1]), operation, 'input', 'input')
            else:
                operator_to_apply = node.children[1]
                CarrierBinding(parse_expression(operator, node.children[0]), operation, 'inputL', 'input')
                CarrierBinding(parse_expression(operator, node.children[2]), operation, 'inputR', 'input')
            operator_to_apply = get_or_create_operator(node_source_code(operator_to_apply))
            CarrierBinding(constant_to_carrier(operator, operator_to_apply), operation, 'operator', 'input')
            output_carrier = CarrierTuft(operator, output_carrier_identifier if output_carrier_identifier else operation.identifier)
            CarrierBinding(output_carrier, operation, 'output', 'output')
            return output_carrier
    tree = parser.parse(bytes(source_code, 'utf8'))
    module = tree.root_node
    function_definition = module.children[0]
    function_name = node_source_code(function_definition.children[1])
    operator_registry[function_name] = operator = Operator(function_name)
    for parameter in function_definition.children[2].children:
        if parameter.type == 'identifier':
            variable = CarrierTuft(operator, node_source_code(parameter))
            CarrierBinding(variable, operator.self_operation, variable.identifier, 'output')
    for statement in function_definition.children[4].children:
        if statement.type == 'expression_statement':
            if statement.children[0].type == 'assignment':
                parse_expression(operator, statement.children[0].children[2].children[0], node_source_code(statement.children[0].children[0].children[0]))
        elif statement.type == 'return_statement':
            for expression in statement.children[1].children:
                variable = parse_expression(operator, expression)
                CarrierBinding(variable, operator.self_operation, variable.identifier, 'input')
    return operator
