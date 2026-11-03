/*
 * Neira's calculator in C.
 *
 * The algorithm is the author's university calculator (2022): the expression is turned into postfix (reverse Polish)
 * notation with an operator stack (Dijkstra's shunting-yard) built from linked lists, then the postfix list is
 * evaluated; syntax errors (two numbers or two operators in a row, empty or unbalanced parentheses) and division by
 * zero are reported. Reworked for Neira (2026): numbers are doubles (15/100*2400 must be 360, not 0), unary minus,
 * powers (** and ^), every node is typed and freed.
 *
 * Usage: echo "2 * (3 + 4)" | calc      prints 14
 *        output on error: "syntax error", "division by zero" or "math error"; exit code 0 / 1 / 2 / 3
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef enum { NUMBER, OPERATOR } NodeType;

typedef struct Node {
    NodeType type;
    double value;   /* for NUMBER */
    char op;        /* for OPERATOR: + - * / ^ ( ) and 'u' = unary minus */
    struct Node *next;
} Node;

/* a list with a tail pointer: used as a stack (push/pop at head) and as the postfix queue (append at tail) */
typedef struct {
    Node *head;
    Node *tail;
} List;

static Node *new_node(NodeType type, double value, char op) {
    Node *node = malloc(sizeof(Node));
    if (node == NULL) {
        fputs("out of memory\n", stderr);
        exit(4);
    }
    node->type = type;
    node->value = value;
    node->op = op;
    node->next = NULL;
    return node;
}

static void push(List *list, Node *node) {
    node->next = list->head;
    list->head = node;
    if (list->tail == NULL) list->tail = node;
}

static Node *pop(List *list) {
    Node *node = list->head;
    if (node != NULL) {
        list->head = node->next;
        if (list->head == NULL) list->tail = NULL;
        node->next = NULL;
    }
    return node;
}

static void append(List *list, Node *node) {
    node->next = NULL;
    if (list->tail == NULL) {
        list->head = list->tail = node;
    } else {
        list->tail->next = node;
        list->tail = node;
    }
}

static void free_list(List *list) {
    Node *node;
    while ((node = pop(list)) != NULL) free(node);
}

static int precedence(char op) {
    switch (op) {
        case '+': case '-': return 1;
        case '*': case '/': return 2;
        case 'u': return 3;           /* -2^2 = -(2^2) = -4, as in mathematics */
        case '^': return 4;
        default: return 0;
    }
}

static int right_associative(char op) { return op == '^' || op == 'u'; }

/* moves operators from the stack to the output while they bind at least as tightly as the incoming one */
static void push_operator(List *output, List *ops, char op) {
    if (op != 'u') {                  /* a prefix operator never pops anything */
        while (ops->head != NULL && ops->head->op != '(') {
            char top = ops->head->op;
            int stronger = precedence(top) > precedence(op);
            int equal_left = precedence(top) == precedence(op) && !right_associative(op);
            if (!stronger && !equal_left) break;
            append(output, pop(ops));
        }
    }
    push(ops, new_node(OPERATOR, 0, op));
}

/* the expression -> postfix list; returns 0 on success, 1 on a syntax error */
static int build_postfix(const char *text, List *output) {
    List ops = {NULL, NULL};
    int expect_operand = 1;           /* at the start, after '(' or after an operator a number must come */
    int depth = 0;
    const char *p = text;
    while (*p) {
        if (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') {
            p++;
        } else if ((*p >= '0' && *p <= '9') || *p == '.') {
            char *end;
            double value = strtod(p, &end);
            if (!expect_operand || end == p) goto syntax_error;   /* two numbers in a row, or a lone '.' */
            append(output, new_node(NUMBER, value, 0));
            p = end;
            expect_operand = 0;
        } else if (*p == '(') {
            if (!expect_operand) goto syntax_error;               /* "2(3)": no implicit multiplication */
            push(&ops, new_node(OPERATOR, 0, '('));
            depth++;
            p++;
        } else if (*p == ')') {
            if (expect_operand || depth == 0) goto syntax_error;  /* "()", "(2+)" or an extra ')' */
            while (ops.head != NULL && ops.head->op != '(') append(output, pop(&ops));
            free(pop(&ops));                                      /* the '(' itself */
            depth--;
            p++;
        } else if (strchr("+-*/^", *p)) {
            char op = *p;
            if (op == '*' && p[1] == '*') {                       /* Python-style power */
                op = '^';
                p++;
            }
            p++;
            if (expect_operand) {
                if (op == '-') push_operator(output, &ops, 'u');
                else if (op == '+') continue;                     /* unary plus changes nothing */
                else goto syntax_error;                           /* two operators in a row */
            } else {
                push_operator(output, &ops, op);
                expect_operand = 1;
            }
        } else {
            goto syntax_error;                                    /* a letter or another symbol */
        }
    }
    if (expect_operand || depth != 0 || output->head == NULL) goto syntax_error;
    while (ops.head != NULL) append(output, pop(&ops));
    return 0;

syntax_error:
    free_list(&ops);
    return 1;
}

/* evaluates the postfix list; 0 = ok, 2 = division by zero, 3 = math error (overflow, 0^-1, ...) */
static int evaluate(List *postfix, double *result) {
    List stack = {NULL, NULL};
    Node *node;
    int status = 0;
    while (status == 0 && (node = pop(postfix)) != NULL) {
        if (node->type == NUMBER) {
            push(&stack, node);
            continue;
        }
        if (node->op == 'u') {
            stack.head->value = -stack.head->value;
            free(node);
            continue;
        }
        Node *right = pop(&stack);
        Node *left = stack.head;                                  /* the result is written into the left operand */
        switch (node->op) {
            case '+': left->value += right->value; break;
            case '-': left->value -= right->value; break;
            case '*': left->value *= right->value; break;
            case '/':
                if (right->value == 0) status = 2;
                else left->value /= right->value;
                break;
            case '^': left->value = pow(left->value, right->value); break;
        }
        if (status == 0 && !isfinite(left->value)) status = 3;
        free(right);
        free(node);
    }
    if (status == 0) *result = stack.head->value;
    free_list(&stack);
    free_list(postfix);
    return status;
}

/* The library entry point (calc.dll): 0 = ok and *result set, 1 = syntax error, 2 = division by zero, 3 = math error.
 * Called in-process from Python through ctypes: no process start per expression (3.9 ms -> microseconds). */
#ifdef _WIN32
__declspec(dllexport)
#endif
int calc_eval(const char *text, double *result) {
    List postfix = {NULL, NULL};
    if (text == NULL || result == NULL) return 1;
    if (build_postfix(text, &postfix)) {
        free_list(&postfix);
        return 1;
    }
    int status = evaluate(&postfix, result);
    if (status == 0 && *result == 0) *result = 0;   /* no "-0" */
    return status;
}

#ifndef CALC_DLL
int main(int argc, char **argv) {
    static char text[4096];
    size_t length;
    if (argc > 1) {                   /* the expression may also come as arguments: calc 2 + 2 */
        text[0] = '\0';
        for (int i = 1; i < argc && strlen(text) + strlen(argv[i]) + 2 < sizeof(text); i++) {
            strcat(text, argv[i]);
            strcat(text, " ");
        }
    } else {
        length = fread(text, 1, sizeof(text) - 1, stdin);
        text[length] = '\0';
    }
    List postfix = {NULL, NULL};
    if (build_postfix(text, &postfix)) {
        free_list(&postfix);
        puts("syntax error");
        return 1;
    }
    double result;
    int status = evaluate(&postfix, &result);
    if (status == 2) {
        puts("division by zero");
        return 2;
    }
    if (status == 3) {
        puts("math error");
        return 3;
    }
    if (result == 0) result = 0;      /* no "-0" */
    printf("%.12g\n", result);
    return 0;
}
#endif
