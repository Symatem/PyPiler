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
        def format_bindings(bindings):
            return {operand: binding.carrier.identifier for operand, binding in bindings.items()}
        return 'Operation<id="{}", in={}, out={}>'.format(self.identifier, format_bindings(self.input_bindings), format_bindings(self.output_bindings))

class CarrierBinding:
    def __init__(self, carrier, operation, operand, type):
        self.carrier = carrier
        self.operation = operation
        self.operand = operand
        if type == 'input':
            carrier.destination_bindings.append(self)
            operation.input_bindings[operand] = self
        elif type == 'output':
            carrier.source_binding = self
            operation.output_bindings[operand] = self

    def __repr__(self):
        return 'CarrierBinding<carrier={}, operation={}, operand={}>'.format(self.carrier.identifier, self.operation.identifier, self.operand)

class CarrierTuft:
    def __init__(self, operator, identifier):
        operator.carriers[identifier] = self
        self.operator = operator
        self.identifier = identifier
        self.source_binding = None
        self.destination_bindings = []

    def __repr__(self):
        return 'CarrierTuft<id="{}", src={}, dst={}>'.format(
            self.identifier,
            {self.source_binding.operand: self.source_binding.operation.identifier},
            {binding.operand: binding.operation.identifier for binding in self.destination_bindings}
        )

def constant_to_carrier(operator, value, output_carrier_identifier=None):
    identifier = 'OpConst<{}>'.format(value.identifier) if isinstance(value, Operator) else 'Literal<{}>'.format(value)
    if identifier in operator.operations:
        return operator.operations[identifier].output_bindings['output']
    operation = Operation(operator, identifier)
    operation.value = value
    carrier = CarrierTuft(operator, output_carrier_identifier if output_carrier_identifier else identifier)
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

    def children_of(self, node):
        return list(filter(lambda x: x.type != 'comment', node.children))

    def resolve_identifier(self, outer_operator, identifier):
        name = self.source_code_of(identifier)
        return  outer_operator.carriers[name] if name in outer_operator.carriers else None

    def parse_expression(self, outer_operator, expression, output_carrier_identifier=None):
        expression_children = self.children_of(expression)
        while expression.type == 'parenthesized_expression':
            expression = expression_children[1]
        if expression.type == 'integer' or expression.type == 'float' or \
           expression.type == 'true' or expression.type == 'false' or \
           expression.type == 'none' or expression.type == 'string':
            return constant_to_carrier(outer_operator, self.source_code_of(expression), output_carrier_identifier)
        elif expression.type == 'tuple' or expression.type == 'generator_expression' or \
             expression.type == 'list' or expression.type == 'list_comprehension' or \
             expression.type == 'set' or expression.type == 'set_comprehension' or \
             expression.type == 'dictionary' or expression.type == 'dictionary_comprehension' or \
             expression.type == 'list_splat' or expression.type == 'dictionary_splat':
            raise ParsingError('Collection literals are not supported', self.source_position_of(expression))
        elif expression.type == 'identifier':
            return self.resolve_identifier(outer_operator, expression)
        elif expression.type == 'call' or expression.type == 'conditional_expression' or \
             expression.type == 'unary_operator' or expression.type == 'not_operator' or \
             expression.type == 'binary_operator' or expression.type == 'boolean_operator' or expression.type == 'comparison_operator':
            operation = Operation(outer_operator, '({}) {}'.format(self.source_code_of(expression), self.source_position_of(expression)))
            operator_to_apply = self.source_code_of(expression_children[0])
            if expression.type == 'call':
                for argument in self.children_of(expression_children[1])[1:-1]:
                    if argument.type == 'keyword_argument':
                        CarrierBinding(self.parse_expression(outer_operator, self.children_of(argument)[2]), operation, self.source_code_of(self.children_of(argument)[0]), 'input')
                    elif argument.type != ',':
                        raise ParsingError('Only keyword arguments are supported', self.source_position_of(expression))
            elif expression.type == 'conditional_expression':
                operator_to_apply = 'conditional'
                CarrierBinding(self.parse_expression(outer_operator, expression_children[0]), operation, 'inputTrue', 'input')
                CarrierBinding(self.parse_expression(outer_operator, expression_children[2]), operation, 'condition', 'input')
                CarrierBinding(self.parse_expression(outer_operator, expression_children[4]), operation, 'inputFalse', 'input')
            elif expression.type == 'unary_operator' or expression.type == 'not_operator':
                CarrierBinding(self.parse_expression(outer_operator, expression_children[1]), operation, 'input', 'input')
            else:
                operator_to_apply = self.source_code_of(expression_children[1])
                CarrierBinding(self.parse_expression(outer_operator, expression_children[0]), operation, 'inputL', 'input')
                CarrierBinding(self.parse_expression(outer_operator, expression_children[2]), operation, 'inputR', 'input')
                if expression.type == 'comparison_operator' and len(expression_children) > 3:
                    raise ParsingError('Multi comparison is not supported', self.source_position_of(expression))
            operator_to_apply = get_or_create_operator(operator_to_apply)
            CarrierBinding(constant_to_carrier(outer_operator, operator_to_apply), operation, 'operator', 'input')
            output_carrier = CarrierTuft(outer_operator, output_carrier_identifier if output_carrier_identifier else operation.identifier)
            CarrierBinding(output_carrier, operation, 'output', 'output')
            return output_carrier
        elif statement.type == 'lambda':
            raise ParsingError('Lambdas are not supported', self.source_position_of(expression))
        else:
            print(expression.sexp())
            raise ParsingError('Unsupported expression', self.source_position_of(expression))

    def parse_block(self, outer_operator, block):
        for statement in self.children_of(block):
            statement_children = self.children_of(statement)
            if statement.type == 'expression_statement':
                if statement_children[0].type == 'assignment':
                    assignment_children = self.children_of(statement_children[0])
                    if assignment_children[0].type != 'expression_list' or assignment_children[1].type != '=' or assignment_children[2].type != 'expression_list':
                        raise ParsingError('Unsupported assignment', self.source_position_of(statement))
                    left_side = self.children_of(assignment_children[0])
                    right_side = self.children_of(assignment_children[2])
                    for i in range(0, len(left_side)):
                        if left_side[i].type == ',':
                            continue
                        if left_side[i].type != 'identifier':
                            raise ParsingError('Only assignments to identifiers are supported', self.source_position_of(statement))
                        if self.resolve_identifier(outer_operator, left_side[i]):
                            raise ParsingError('Only single static assignment is supported', self.source_position_of(statement))
                        self.parse_expression(outer_operator, right_side[i], self.source_code_of(left_side[i]))
                else:
                    raise ParsingError('Unsupported expression statement', self.source_position_of(statement))
            elif statement.type == 'function_definition':
                raise ParsingError('Nested function definitions are not supported', self.source_position_of(statement))
            elif statement.type == 'if_statement' or statement.type ==  'while_statement' or statement.type == 'for_statement' or \
                 statement.type == 'break_statement' or statement.type == 'continue_statement':
                raise ParsingError('Control flow is not supported', self.source_position_of(statement))
            elif statement.type == 'try_statement' or statement.type ==  'with_statement' or statement.type == 'raise_statement':
                raise ParsingError('Exceptions are not supported', self.source_position_of(statement))
            elif statement.type == 'return_statement':
                if statement != self.children_of(block)[-1]:
                    raise ParsingError('Early return is not supported', self.source_position_of(statement))
                for expression in self.children_of(statement_children[1]):
                    variable = self.parse_expression(outer_operator, expression)
                    CarrierBinding(variable, outer_operator.self_operation, 'output', 'input')
            elif statement.type != 'pass_statement':
                print(statement.sexp())
                raise ParsingError('Unsupported statement', self.source_position_of(statement))

    def parse_function_definition(self, function_definition):
        function_name = self.source_code_of(self.children_of(function_definition)[1])
        operator_registry[function_name] = operator = Operator(function_name)
        for parameter in self.children_of(self.children_of(function_definition)[2])[1:-1]:
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
        self.parse_block(operator, self.children_of(function_definition)[4])
        return operator
