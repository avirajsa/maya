"""Calculator tool — safe math expression evaluator."""

import ast
import math
import operator
from typing import Any
from langchain_core.tools import tool

# Supported operators mapped to operator functions
SAFE_OPERATORS: dict[type[ast.AST], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Supported mathematical functions
SAFE_FUNCTIONS: dict[str, Any] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
}

# Supported constants
SAFE_CONSTANTS: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}


class SafeEvaluator(ast.NodeVisitor):
    """Safely evaluates an abstract syntax tree using only approved math operations.

    Disallows function definitions, imports, variable assignment, and any unauthorized calls.
    """

    def evaluate(self, node: ast.AST) -> Any:
        """Evaluate an AST expression node."""
        return self.visit(node)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    def visit_Num(self, node: Any) -> Any:
        # Fallback for older python AST nodes
        return node.n

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")

        left = self.visit(node.left)
        right = self.visit(node.right)

        # Protection against excessive exponentiation
        if op_type is ast.Pow:
            if isinstance(right, (int, float)) and right > 1000:
                raise ValueError("Exponent too large (maximum allowed is 1000).")
            if isinstance(left, (int, float)) and abs(left) > 1e10 and right > 10:
                raise ValueError("Exponentiation base and power would cause overflow.")

        return SAFE_OPERATORS[op_type](left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = self.visit(node.operand)
        return SAFE_OPERATORS[op_type](operand)

    def visit_Name(self, node: ast.Name) -> Any:
        name = node.id
        if name in SAFE_CONSTANTS:
            return SAFE_CONSTANTS[name]
        raise ValueError(f"Undefined variable or constant: '{name}'")

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct mathematical functions are allowed.")
        func_name = node.func.id
        if func_name not in SAFE_FUNCTIONS:
            raise ValueError(f"Function '{func_name}' is not allowed or supported.")

        func = SAFE_FUNCTIONS[func_name]
        args = [self.visit(arg) for arg in node.args]
        return func(*args)

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"Syntax construct '{type(node).__name__}' is not permitted.")


def _safe_calculate(expression: str) -> str:
    """Internal implementation of safe calculation."""
    cleaned = expression.strip()
    if not cleaned:
        return "Error: Empty expression provided."

    try:
        parsed = ast.parse(cleaned, mode="eval")
    except SyntaxError:
        return "Error: Invalid mathematical expression"
    except Exception as e:
        return f"Error: Failed to parse expression ({e})"

    evaluator = SafeEvaluator()
    try:
        result = evaluator.evaluate(parsed)
        if isinstance(result, (int, float)):
            return str(result)
        return str(result)
    except ZeroDivisionError:
        return "Error: Division by zero."
    except OverflowError:
        return "Error: Calculation resulted in an overflow."
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def calculate(expression: str) -> str:
    """Safely calculate and evaluate a mathematical expression.

    Use this tool whenever you need to compute numbers, percentages, trigonometry,
    logarithms, or algebraic equations. Supports +, -, *, /, **, //, %, unary minus,
    parentheses, and functions like sin, cos, sqrt, log, abs, round, etc.

    Args:
        expression: Mathematical expression string to evaluate (e.g. '2 + 2', '(10 * 5) / 2 + 3 ** 2').

    Returns:
        Formatted calculation result string or a clear error message.
    """
    return _safe_calculate(expression)
