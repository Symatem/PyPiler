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
        return 'Operator<id="{}",\n\toperations=[{}\n\t],\n\tcarriers=[{}\n\t]\n>'.format(
            self.identifier,
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

class ParsingError(Exception):
    def __init__(self, message, source_position):
        super().__init__('{}: {}'.format(message, source_position))

class CompileUnit:
    def __init__(self, value):
        self.source_code = inspect.getsource(value)
        self.ast = parser.parse(bytes(self.source_code, 'utf8'))

    def source_code_of(self, node):
        return self.source_code[node.start_byte:node.end_byte]

    def source_position_of(self, node):
        return '{}:{}'.format(node.start_point[0]+1, node.start_point[1]+1)

    def parse_expression(self, outer_operator, expression, output_carrier_identifier=None):
        while expression.type == 'parenthesized_expression':
            expression = expression.children[1]
        if expression.type == 'integer' or expression.type == 'float' or expression.type == 'true' or expression.type == 'false' or expression.type == 'none' or expression.type == 'string':
            return constant_to_carrier(outer_operator, self.source_code_of(expression))
        elif expression.type == 'tuple' or expression.type == 'generator_expression' or \
             expression.type == 'list' or expression.type == 'list_comprehension' or \
             expression.type == 'set' or expression.type == 'set_comprehension' or \
             expression.type == 'dictionary' or expression.type == 'dictionary_comprehension' or \
             expression.type == 'list_splat' or expression.type == 'dictionary_splat':
            raise ParsingError('Collection literals are not supported', self.source_position_of(expression))
        elif expression.type == 'identifier':
            return outer_operator.carriers[self.source_code_of(expression)]
        elif expression.type == 'call' or expression.type == 'unary_operator' or expression.type == 'not_operator' or expression.type == 'binary_operator' or expression.type == 'boolean_operator' or expression.type == 'comparison_operator':
            operation = Operation(outer_operator, '({}) {}'.format(self.source_code_of(expression), self.source_position_of(expression)))
            operator_to_apply = expression.children[0]
            if expression.type == 'call':
                for argument in expression.children[1].children[1:-1]:
                    if argument.type == 'keyword_argument':
                        CarrierBinding(self.parse_expression(outer_operator, argument.children[2]), operation, self.source_code_of(argument.children[0]), 'input')
                    elif argument.type != ',':
                        raise ParsingError('Only keyword arguments are supported', self.source_position_of(expression))
            elif expression.type == 'unary_operator' or expression.type == 'not_operator':
                CarrierBinding(self.parse_expression(outer_operator, expression.children[1]), operation, 'input', 'input')
            else:
                operator_to_apply = expression.children[1]
                CarrierBinding(self.parse_expression(outer_operator, expression.children[0]), operation, 'inputL', 'input')
                CarrierBinding(self.parse_expression(outer_operator, expression.children[2]), operation, 'inputR', 'input')
                if expression.type == 'comparison_operator' and len(expression.children) > 3:
                    raise ParsingError('Multi comparison is not supported', self.source_position_of(expression))
            operator_to_apply = get_or_create_operator(self.source_code_of(operator_to_apply))
            CarrierBinding(constant_to_carrier(outer_operator, operator_to_apply), operation, 'operator', 'input')
            output_carrier = CarrierTuft(outer_operator, output_carrier_identifier if output_carrier_identifier else operation.identifier)
            CarrierBinding(output_carrier, operation, 'output', 'output')
            return output_carrier
        elif statement.type == 'conditional_expression':
            raise ParsingError('Conditionals are not supported', self.source_position_of(expression))
        elif statement.type == 'lambda':
            raise ParsingError('Lambdas are not supported', self.source_position_of(expression))
        else:
            print(expression.sexp())
            raise ParsingError('Unsupported expression', self.source_position_of(expression))

    def parse_block(self, outer_operator, block):
        for statement in block.children:
            if statement.type == 'expression_statement':
                if statement.children[0].type == 'assignment' and statement.children[0].children[0].type == 'expression_list' and statement.children[0].children[2].type == 'expression_list':
                    if len(statement.children[0].children[0].children) > 1:
                        raise ParsingError('Multi assignments are not supported', self.source_position_of(statement))
                    if statement.children[0].children[0].children[0].type != 'identifier':
                        raise ParsingError('Only assignments to identifiers are supported', self.source_position_of(statement))
                    self.parse_expression(outer_operator, statement.children[0].children[2].children[0], self.source_code_of(statement.children[0].children[0].children[0]))
                else:
                    raise ParsingError('Unsupported expression statement', self.source_position_of(statement))
            elif statement.type == 'function_definition':
                raise ParsingError('Nested function definitions are not supported', self.source_position_of(statement))
            elif statement.type == 'if_statement' or statement.type ==  'while_statement' or statement.type == 'for_statement' or statement.type == 'break_statement' or statement.type == 'continue_statement':
                raise ParsingError('Control flow is not supported', self.source_position_of(statement))
            elif statement.type == 'try_statement' or statement.type ==  'with_statement' or statement.type == 'raise_statement':
                raise ParsingError('Exceptions are not supported', self.source_position_of(statement))
            elif statement.type == 'return_statement':
                if statement != block.children[-1]:
                    raise ParsingError('Early return is not supported', self.source_position_of(statement))
                for expression in statement.children[1].children:
                    variable = self.parse_expression(outer_operator, expression)
                    CarrierBinding(variable, outer_operator.self_operation, 'output', 'input')
            elif statement.type != 'pass_statement':
                print(statement.sexp())
                raise ParsingError('Unsupported statement', self.source_position_of(statement))

    def parse_function_definition(self, function_definition):
        function_name = self.source_code_of(function_definition.children[1])
        operator_registry[function_name] = operator = Operator(function_name)
        for parameter in function_definition.children[2].children[1:-1]:
            if parameter.type == 'identifier':
                variable = CarrierTuft(operator, self.source_code_of(parameter))
                CarrierBinding(variable, operator.self_operation, variable.identifier, 'output')
            elif parameter.type == 'typed_parameter':
                raise ParsingError('Typed parameters are not supported', self.source_position_of(parameter))
            elif parameter.type == 'default_parameter':
                raise ParsingError('Default parameters are not supported', self.source_position_of(parameter))
            elif parameter.type == 'list_splat' or parameter.type == 'dictionary_splat':
                raise ParsingError('List splat and dict splat parameters are not supported', self.source_position_of(parameter))
            elif parameter.type != ',':
                print(parameter.sexp())
                raise ParsingError('Unsupported parameter', self.source_position_of(parameter))
        self.parse_block(operator, function_definition.children[4])
        return operator
