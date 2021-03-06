from typing import List
from scanning.error import *
from intermediate.tokens import *
from intermediate.lookup_tables import *
from .expressions import *
from .statements import *

types = [tokens.BYTE, tokens.SHORT, tokens.INT,
         tokens.LONG, tokens.BOOL, tokens.STR]
inc_dec_tokens = [tokens.EQUAL, tokens.PLUS_EQUAL,
                  tokens.MINUS_EQUAL, tokens.STAR_EQUAL, tokens.SLASH_EQUAL]


class Parser():
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.current = 0

        # data for keeping track of loops
        self.in_loop = False
        self.loop_index_begin = 0
        self.loop_index_end = 0

        # function data
        self.in_func = False
        self.func_name = ""

    # returns last - 1 token

    def previous(self) -> Token:
        return self.tokens[self.current - 1]

    # check if were at the end of the tokens
    def is_at_end(self) -> bool:
        return self.peek().type == tokens.EOF

    # returns current token
    def peek(self) -> Token:
        return self.tokens[self.current]

    # checks if current token is equal to given token
    def check(self, token: tokens) -> bool:
        if self.is_at_end():
            return False
        return self.peek().type == token

    # advances current token to next token
    def advance(self) -> None:
        self.current += 1

    def match(self, *tokens: tokens):
        for token in tokens:
            if self.check(token):
                self.advance()
                return True
        return False

    def assert_prev(self, condition: bool, message: str) -> None:
        assert_error(condition, self.previous(), message)

    def assert_curr(self, condition: bool, message: str) -> None:
        assert_error(condition, self.peek(), message)

    def consume(self, token: tokens, message: str) -> None:
        assert_error(self.check(token), self.previous(), message)
        self.advance()
        return self.previous()

    def primary(self) -> Expr:
        if self.match(tokens.FALSE):
            return LiteralExpr(False, tokens.BOOL)
        if self.match(tokens.TRUE):
            return LiteralExpr(True, tokens.BOOL)
        if self.match(tokens.NULL):
            return LiteralExpr(None)
        if self.match(tokens.NUMBER):
            return LiteralExpr(self.previous(), tokens.INT)
        if self.match(tokens.LEFT_PAREN):
            expr = self.expression()
            self.consume(tokens.RIGHT_PAREN, "Expected ')' after expression.")
            return GroupingExpr(expr)
        if self.match(tokens.IDENTIFIER):
            return VarExpr(self.previous())
        if self.match(tokens.STAR):
            expr = self.expression()
            return DereferenceExpr(expr)
        if self.match(tokens.LOGICAL_AND):
            token = self.consume(tokens.IDENTIFIER, "Expected variable name.")
            return VarToPointerExpr(token)
        if self.match(tokens.STRING):
            return LiteralExpr(self.previous(), tokens.STRING)
        if self.match(tokens.CHAR):
            char = self.previous()
            char.literal = ord(char.literal)
            return LiteralExpr(char, tokens.CHAR)
        if self.match(tokens.SYSCALL):
            return self.syscall_stmt()

        # if no valid token is found, throw error
        error(self.peek(), "Expected expression.")

    def finish_call(self, expr: Expr) -> Expr:
        args = []
        if not self.check(tokens.RIGHT_PAREN):
            while True:
                args.append(self.expression())
                if self.match(tokens.RIGHT_PAREN):
                    return CallExpr(expr, args)
                self.consume(
                    tokens.COMMA, "Expected ',' after function argument.")

        self.consume(tokens.RIGHT_PAREN,
                     "Expected ')' after function arguments.")
        return CallExpr(expr, args)

    def array_access(self, expr: Expr) -> Expr:
        index = self.expression()
        self.consume(tokens.RIGHT_SQUARE, "Expected ']' after array index.")

        if self.match(*inc_dec_tokens):
            operator = self.previous()
            val = self.expression()
            node = AssignmentExpr(expr.name, operator, val, "array", index)
            return node

        return ArrayAccessExpr(expr.name, index)

    def call(self) -> Expr:
        expr = self.primary()

        if self.match(tokens.LEFT_SQUARE):
            return self.array_access(expr)

        if self.match(tokens.LEFT_PAREN) and isinstance(expr, VarExpr):
            expr = self.finish_call(expr)

        return expr

    def unary(self) -> Expr:
        if self.match(tokens.MINUS, tokens.BANG):
            operator = self.previous()
            right = self.unary()
            return UnaryExpr(operator, right)
        return self.call()

    def factor(self) -> Expr:
        expr = self.unary()

        while self.match(tokens.SLASH, tokens.STAR):
            operator = self.previous()
            right = self.unary()
            expr = BinaryExpr(expr, operator, right)

        return expr

    def term(self) -> Expr:
        expr = self.factor()

        while self.match(tokens.PLUS, tokens.MINUS,
                         tokens.PERCENT, tokens.LOGICAL_OR, tokens.LOGICAL_AND):
            operator = self.previous()
            right = self.factor()
            expr = BinaryExpr(expr, operator, right)

        return expr

    def comparison(self) -> Expr:
        expr = self.term()

        while self.match(tokens.GREATER, tokens.GREATER_EQUAL, tokens.LESS, tokens.LESS_EQUAL):
            operator = self.previous()
            right = self.term()
            expr = BinaryExpr(expr, operator, right, True)

        return expr

    # parses equalities or anything above that
    def equality(self) -> Expr:
        expr = self.comparison()
        while self.match(tokens.EQUAL_EQUAL, tokens.BANG_EQUAL):
            operator = self.previous()
            right = self.expression()
            expr = BinaryExpr(expr, operator, right, True)
        return expr

    def assignment(self) -> Expr:
        expr = self.equality()

        if self.match(*inc_dec_tokens):
            operator = self.previous()
            right = self.assignment()

            assert_error(isinstance(expr, VarExpr), operator, "Invalid assignment target.")
            return AssignmentExpr(expr.name, operator, right)

        return expr

    def expression(self) -> Expr:
        expr = self.assignment()
        return expr

    def print_stmt(self) -> Stmt:
        expr = self.expression()
        self.consume(tokens.SEMICOLON,
                     "Expected ';' after 'print' expression.")
        return PrintStmt(expr)

    def expression_stmt(self) -> Stmt:
        expr = self.expression()
        self.consume(tokens.SEMICOLON, "Expected ';' after expression.")
        return ExprStmt(expr)

    def block(self) -> Stmt:
        statements = []
        while not self.check(tokens.RIGHT_BRACE) and not self.is_at_end():
            statements.append(self.declaration())
        self.consume(tokens.RIGHT_BRACE, "Expected '}' after block.")
        return BlockStmt(statements)

    def if_stmt(self) -> Stmt:
        self.consume(tokens.LEFT_PAREN, "Expected '(' after 'if'.")
        condition = self.expression()
        self.consume(tokens.RIGHT_PAREN, "Expected ')' after if condition.")
        then_branch = self.statement()

        elif_statements = []
        while self.match(tokens.ELIF):
            elif_index = self.current - 1
            self.consume(tokens.LEFT_PAREN, "Expected '(' after 'elseif'.")
            econdition = self.expression()
            self.consume(tokens.RIGHT_PAREN,
                         "Expected ')' after elseif condition.")
            ethen_branch = self.statement()
            # self.current is used to generate a unique label for each elif statement
            elif_statements.append((econdition, ethen_branch, elif_index))

        else_branch = None
        else_id = None
        if self.match(tokens.ELSE):
            else_id = self.current - 1
            else_branch = self.statement()

        stmt = IfStmt(condition, then_branch, elif_statements, else_branch)
        stmt.end_id = self.current
        if else_branch:
            stmt.else_id = else_id
        return stmt

    def while_stmt(self) -> Stmt:
        while_index = self.current - 1
        self.loop_index_begin = while_index
        self.consume(tokens.LEFT_PAREN, "Expected '(' after 'while'.")
        condition = self.expression()
        self.consume(tokens.RIGHT_PAREN, "Expected ')' after while condition.")
        self.in_loop = True  # let parser know that were in a loop
        body = self.statement()
        end_index = self.current
        stmt = WhileStmt(condition, body, while_index, end_index)
        self.in_loop = False
        return stmt

    def for_stmt(self) -> Stmt:
        for_index = self.current
        self.loop_index_begin = for_index
        self.consume(tokens.LEFT_PAREN, "Expected '(' after 'for'.")
        initializer = None
        if self.match(tokens.SEMICOLON):
            initializer = None
        elif self.match(*types):
            initializer = self.var_declaration()
        else:
            initializer = self.expression_stmt()

        condition = None
        if not self.check(tokens.SEMICOLON):
            condition = self.expression()
        self.consume(tokens.SEMICOLON, "Expected ';' after for condition.")

        increment = None
        if not self.check(tokens.RIGHT_PAREN):
            increment = self.expression()
        self.consume(tokens.RIGHT_PAREN, "Expected ')' after for increment.")

        self.in_loop = True  # let parser know that were in a loop
        body = self.statement()  # while loob body
        end_index = self.current
        self.in_loop = False

        if increment != None:  # put increment after body
            body = BlockStmt([body, ExprStmt(increment)])
        if condition == None:
            condition = LiteralExpr(True)
        body = WhileStmt(condition, body, for_index, end_index)
        if initializer != None:
            body = BlockStmt([initializer, body])

        return body

    def break_stmt(self) -> Stmt:
        self.consume(tokens.SEMICOLON, "Expected ';' after 'break'.")
        self.assert_prev(self.in_loop, "Cannot use 'break' outside of loop.")
        return BreakStmt()

    def continue_stmt(self) -> Stmt:
        self.consume(tokens.SEMICOLON, "Expected ';' after 'continue'.")
        self.assert_prev(self.in_loop, "Cannot use 'continue' outside of loop.")
        return ContinueStmt(self.loop_index_begin)

    def syscall_stmt(self) -> Stmt:
        self.consume(
            tokens.NUMBER, "Expected number after 'syscall' (syscall ID).")
        syscall_id = self.previous().literal
        args = []
        if not self.check(tokens.SEMICOLON):
            args.append(self.expression())
            while self.match(tokens.COMMA):
                args.append(self.expression())

        self.assert_prev(len(args) == 0, "Expected at least one argument after syscall ID.")
        return SyscallStmt(syscall_id, args)

    def return_stmt(self) -> Stmt:
        self.assert_curr(self.in_func, "Cannot use 'return' outside of function.")
        expr = None
        if not self.check(tokens.SEMICOLON):
            expr = self.expression_stmt()
        else:
            self.consume(tokens.SEMICOLON,
                         "Expected ';' after return expression.")
        return ReturnStmt(expr, self.func_name)

    def asm_stmt(self) -> Stmt:
        self.consume(tokens.LEFT_BRACE, "Expected '{' after 'asm'.")
        lines = []
        while not self.check(tokens.RIGHT_BRACE) and not self.is_at_end():
            lines.append(self.consume(
                tokens.STRING, "Expected string after 'asm'"))
        self.consume(tokens.RIGHT_BRACE, "Expected '}' after 'asm'.")
        return AsmStmt(lines)


    def extern_stmt(self) -> Stmt:
        self.assert_prev(self.match(*types, tokens.VOID), "Expected type for 'extern' statement.")
        return_type = self.previous().type
        name = self.consume(tokens.IDENTIFIER,
                            "Expected identifier after 'extern'.")
        self.consume(tokens.LEFT_PAREN, "Expected '(' after function name.")
        params = self.params()
        self.consume(tokens.RIGHT_PAREN,
                     "Expected ')' after function parameters.")
        self.consume(tokens.SEMICOLON, "Expected ';' after 'extern'.")
        return ExternStmt(name, return_type, params)

    def statement(self) -> Stmt:
        if self.match(tokens.PRINT):
            return self.print_stmt()
        if self.match(tokens.LEFT_BRACE):
            return self.block()
        if self.match(tokens.IF):
            return self.if_stmt()
        if self.match(tokens.WHILE):
            return self.while_stmt()
        if self.match(tokens.FOR):
            return self.for_stmt()
        if self.match(tokens.BREAK):
            return self.break_stmt()
        if self.match(tokens.CONTINUE):
            return self.continue_stmt()
        if self.match(tokens.RETURN):
            return self.return_stmt()
        if self.match(tokens.ASM):
            return self.asm_stmt()
        if self.match(tokens.EXTERN):
            return self.extern_stmt()

        return self.expression_stmt()

    def var_declaration(self) -> Stmt:
        type_ = self.previous()
        size = type_to_size.get(type_.type, None)
        name = self.consume(tokens.IDENTIFIER, "Expected variable name.")
        expr = None

        # parse array size if it is an array
        if self.match(tokens.LEFT_SQUARE):
            expr = self.consume(tokens.NUMBER, "Expected array size.")
            self.consume(tokens.RIGHT_SQUARE, "Expected ']' after array size.")

        initializers = []

        if self.match(tokens.EQUAL):
            if expr:  # array
                self.consume(tokens.LEFT_BRACE,
                             "Expected '{' after array init.")
                while not self.check(tokens.RIGHT_BRACE):
                    self.assert_curr(len(initializers) + 1 >= expr.literal, "Array size exceeded.")
                    initializers.append(self.expression())
                    if self.match(tokens.COMMA):
                        continue
                    if self.match(tokens.RIGHT_BRACE):
                        self.consume(tokens.SEMICOLON,
                                     "Expected ';' after array init.")
                        break
                    error(self.peek(), "Expected ',' or '}' after array initializer.")
                return ArrayStmt(type_, name, initializers, expr.literal * size)
            expr = self.expression()

        if type_ == tokens.STR and expr == None:
            expr = '0'

        self.consume(tokens.SEMICOLON,
                     "Expected ';' after variable declaration.")

        if isinstance(expr, Token):  # uninitialized array
            return ArrayStmt(type_, name, [], expr.literal * size)

        return VarStmt(type_, name, expr, size)

    def params(self) -> List[VarStmt]:
        params = []
        if not self.check(tokens.RIGHT_PAREN):
            # check if parameter type wasn given
            self.assert_curr(self.match(*types), "Expected type before parameter name.")
            type_ = self.previous()
            arg_name = self.consume(
                tokens.IDENTIFIER, "Expected parameter name.")
            size = type_to_size[type_.type]
            if self.match(tokens.LEFT_SQUARE):
                self.consume(tokens.RIGHT_SQUARE,
                             "Expected ']' after array parameter.")
                param = ArrayStmt(type_, arg_name, [], 8)
                param.is_in_func = True
                params.append(param)
            else:
                param = VarStmt(type_, arg_name, None, size)
                params.append(param)
            while self.match(tokens.COMMA):
                self.assert_curr(self.match(*types), "Expected type before parameter name.")
                type_ = self.previous()
                arg_name = self.consume(
                    tokens.IDENTIFIER, "Expected parameter name.")
                size = type_to_size[type_.type]
                if self.match(tokens.LEFT_SQUARE):
                    self.consume(tokens.RIGHT_SQUARE,
                                 "Expected ']' after array parameter.")
                    param = ArrayStmt(type_, arg_name, [], 8)
                    param.is_in_func = True
                    params.append(param)
                else:
                    param = VarStmt(type_, arg_name, None, size)
                    params.append(param)
        return params

    def func_declaration(self) -> Stmt:
        self.assert_curr(self.match(*types, tokens.VOID), "Expected return type after 'func'.")
        return_type = self.previous().type
        name = self.consume(tokens.IDENTIFIER, "Expected function name.")
        self.consume(tokens.LEFT_PAREN, "Expected '(' after function name.")
        params = self.params()
        self.consume(tokens.RIGHT_PAREN, "Expected ')' after parameters.")
        self.consume(tokens.LEFT_BRACE, "Expected '{' before function body.")
        self.in_func = True
        self.func_name = name
        body = self.block()
        self.in_func = False
        return FuncStmt(name, params, body, return_type)

    def declaration(self) -> Stmt:
        if self.match(*types):
            return self.var_declaration()
        if self.match(tokens.FUNC):
            return self.func_declaration()
        return self.statement()

    def parse(self) -> List[Stmt]:
        statements = []

        while not self.is_at_end():
            statements.append(self.declaration())

        return statements
