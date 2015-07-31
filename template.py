import re

VAR_FRAGMENT = 0
OPEN_BLOCK_FRAGMENT = 1
CLOSE_BLOCK_FRAGMENT = 2
TEXT_FRAGMENT = 3
COMMENT_FRAGMENT = 4

VAR_TOKEN_START = '{{'
VAR_TOKEN_END = '}}'
COMMENT_TOKEN_START = '{#'
COMMENT_TOKEN_END = '#}'
BLOCK_TOKEN_START = '{%'
BLOCK_TOKEN_END = '%}'

TOK_REGEX = re.compile(r'(%s.*?%s|%s.*?%s|%s.*?%s)' % (
    VAR_TOKEN_START,
    VAR_TOKEN_END,
    BLOCK_TOKEN_START,
    BLOCK_TOKEN_END,
    COMMENT_TOKEN_START,
    COMMENT_TOKEN_END
))

WHITESPACE = re.compile('\s+')


class TemplateError(Exception):
    pass


class TemplateNotFoundError(TemplateError):
    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "cannot find template file: '%s'" % self.path


class TemplateContextError(TemplateError):
    def __init__(self, context_var):
        self.context_var = context_var

    def __str__(self):
        return "cannot resolve '%s'" % self.context_var


class TemplateSyntaxError(TemplateError):
    def __init__(self, error_syntax):
        self.error_syntax = error_syntax

    def __str__(self):
        return "'%s' seems like invalid syntax" % self.error_syntax


class _Fragment:
    def __init__(self, raw_text):
        self.raw = raw_text
        self.clean = self.clean_fragment()

    def clean_fragment(self):
        if self.raw[:2] in (VAR_TOKEN_START, BLOCK_TOKEN_START):
            return self.raw.strip()[2:-2].strip()
        return self.raw

    @property
    def type(self):
        raw_start = self.raw[:2]
        if raw_start == VAR_TOKEN_START:
            return VAR_FRAGMENT
        elif raw_start == BLOCK_TOKEN_START:
            return CLOSE_BLOCK_FRAGMENT if self.clean[:3] == 'end' else OPEN_BLOCK_FRAGMENT
        elif raw_start == COMMENT_TOKEN_START:
            return COMMENT_FRAGMENT
        else:
            return TEXT_FRAGMENT


class _Node:
    creates_scope = False

    def __init__(self, fragment=None):
        self.children = []
        self.process_fragment(fragment)

    def process_fragment(self, fragment):
        pass

    def enter_scope(self):
        pass

    def render(self, context):
        pass

    def exit_scope(self):
        pass

    def render_children(self, context, children=None):
        if children is None:
            children = self.children

        def render_child(child):
            child_html = child.render(context)
            return '' if not child_html else str(child_html)
        return ''.join(map(render_child, children))


class _ScopableNode(_Node):
    creates_scope = True


class _Root(_Node):
    def render(self, context):
        return self.render_children(context)


class _Text(_Node):
    def process_fragment(self, fragment):
        self.text = fragment

    def render(self, context):
        return self.text


class _Variable(_Node):
    def process_fragment(self, fragment):
        self.name = fragment
        # self.filter_callbacks = []

    def render(self, context):
        value = eval(self.name, context, {})
        # filtered_value = value
        # for callback in self.filter_callbacks:
        #     filtered_value = callback(filtered_value, *args, **kw)
        # return filtered_value

        return value


class _Comment(_Node):
    def render(self, context):
        return ''


class _Set(_ScopableNode):

    def process_fragment(self, fragment):
        _, expr = WHITESPACE.split(fragment, 1)
        self.var_name, self.value = expr.split('=')

    def render(self, context):
        # ...
        eval_value = eval(self.value, context, {})
        new_dict = eval('dict(%s=eval_value)' % self.var_name)
        set_context = context.copy()
        set_context.update(new_dict)
        return self.render_children(set_context)


class _For(_ScopableNode):
    def process_fragment(self, fragment):
        try:
            bits = WHITESPACE.split(fragment)
            self.loop_var = bits[1]
            self.raw_expr = bits[3]
        except ValueError:
            raise TemplateSyntaxError(fragment)

    def render(self, context):
        items = eval(self.raw_expr, context, {})

        def render_item(item):
            inner_context = context.copy()
            inner_context.update({self.loop_var: item})
            return self.render_children(inner_context)
        return ''.join(map(render_item, items))


class _If(_ScopableNode):
    def process_fragment(self, fragment):
        self.expr = fragment.split()[1]

    def render(self, context):
        for branch in self.branches:
            con_bit = eval(branch[0], context, {})
            if con_bit:
                return self.render_children(context, branch[1])

    def exit_scope(self):
        self.branches = self.split_children()

    def split_children(self):
        """
        branches:
        a list that stores expr-branch pairs: [[if-expr,if-branch],[elif-expr,elif-branch],...[else-branch,else-branch]]
        """
        branches = []
        branch = []
        expr = self.expr
        for child in self.children:
            if isinstance(child, (_Elif, _Else)):
                branches.append([expr, branch])
                branch = []
                expr = child.expr
                continue
            branch.append(child)
        else:
            branches.append([expr, branch])
        return branches


class _Elif(_Node):
    def process_fragment(self, fragment):
        self.expr = fragment.split()[1]

    def render(self, context):
        pass


class _Else(_Node):
    def process_fragment(self, fragment):
        self.expr = '1'

    def render(self, context):
        pass


class _Raw(_ScopableNode):
    def process_fragment(self, fragment):
        pass

    def render(self, context):
        print(self.children)


class _Call(_Node):
    def process_fragment(self, fragment):
        try:
            bits = WHITESPACE.split(fragment)
            self.callable = bits[1]
            self.args, self.kwargs = self._parse_params(bits[2:])
        except (ValueError, IndexError):
            raise TemplateSyntaxError(fragment)

    def _parse_params(self, params):
        args, kwargs = [], {}
        for param in params:
            if '=' in param:
                name, value = param.split('=')
                kwargs[name] = eval_expression(value)
            else:
                args.append(eval_expression(param))
        return args, kwargs

    def render(self, context):
        resolved_args, resolved_kwargs = [], {}
        for kind, value in self.args:
            if kind == 'name':
                value = resolve(value, context)
            resolved_args.append(value)
        for key, (kind, value) in self.kwargs.items():
            if kind == 'name':
                value = resolve(value, context)
            resolved_kwargs[key] = value
        resolved_callable = resolve(self.callable, context)
        if hasattr(resolved_callable, '__call__'):
            return resolved_callable(*resolved_args, **resolved_kwargs)
        else:
            raise TemplateError("'%s' is not a callable" % self.callable)


class Compiler:
    def __init__(self, template_string):
        self.template_string = template_string

    def each_fragment(self):
        for fragment in TOK_REGEX.split(self.template_string):
            if fragment:
                yield _Fragment(fragment)

    def compile(self):
        root = _Root()
        scope_stack = [root]
        for fragment in self.each_fragment():
            if not scope_stack:
                raise TemplateError('nesting issues')
            parent_scope = scope_stack[-1]
            if fragment.type == CLOSE_BLOCK_FRAGMENT:
                parent_scope.exit_scope()
                scope_stack.pop()
                continue
            new_node = self.create_node(fragment)
            if new_node:
                parent_scope.children.append(new_node)
                if new_node.creates_scope:
                    scope_stack.append(new_node)
                    new_node.enter_scope()
        return root

    def create_node(self, fragment):
        node_class = None
        if fragment.type == TEXT_FRAGMENT:
            node_class = _Text
        elif fragment.type == VAR_FRAGMENT:
            node_class = _Variable
        elif fragment.type == COMMENT_FRAGMENT:
            node_class = _Comment
        elif fragment.type == OPEN_BLOCK_FRAGMENT:
            cmd = fragment.clean.split()[0]
            if cmd == 'for':
                node_class = _For
            elif cmd == 'if':
                node_class = _If
            elif cmd == 'elif':
                node_class = _Elif
            elif cmd == 'else':
                node_class = _Else
            elif cmd == 'call':
                node_class = _Call
            elif cmd == 'set':
                node_class = _Set
            elif cmd == 'raw':
                node_class = _Raw
            else:
                pass
        if node_class is None:
            raise TemplateSyntaxError(fragment)
        return node_class(fragment.clean)


class MiniTemplate:
    global_context = {}

    def __init__(self, contents=None):
        self.contents = contents
        self.root = Compiler(contents).compile()
        # print(self.root.children)

    # The injected context will be replaced by the local context.
    @classmethod
    def inject(cls, name, value):
        if not isinstance(name, str):
            raise Exception("<class 'str'> expected, but type of %s is %s." % (name, type(name)))
        cls.global_context[name] = value

    def render(self, **kwargs):
        merged_kwargs = self.global_context.copy()
        merged_kwargs.update(kwargs)
        return self.root.render(merged_kwargs)


if __name__ == '__main__':

    var = 'testfool'
    foo = 'caa'

    persons = ['cymoo', 'colleen']
    raw = r"""
    {% set var = 14 %}
    {% if var==14 %}
    if
    {% end %}
    {% end %}
    """
    frags = TOK_REGEX.split(raw)
    print(frags)
    template = MiniTemplate(raw)
    html = template.render(persons=persons, foo=foo)
    print(html)