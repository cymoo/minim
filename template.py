import re
import math
import os
import ast

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

WHITESPACE = re.compile(r'\s+')
NEWLINE = re.compile(r'^\s*\n')

# FILTER_REGEX = re.compile(r'\|')

# STRIP = re.compile(r'(?=\{%.*?%\}\s*)\n')


class TemplateError(Exception):
    pass


class TemplateContextError(TemplateError):
    def __init__(self, context_var):
        self.context_var = context_var

    def __str__(self):
        return "cannot resolve '%s'" % self.context_var


class TemplateFilterError(TemplateError):
    def __init__(self, filter_func):
        self.filter_func = filter_func

    def __str__(self):
        return "cannot apply filter '%s'; the filter does not exist or the parameters are not correct."\
               % self.filter_func


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
        self.frag = fragment
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

    def remove_newline(self):
        # if self.children:
        #     child = self.children[0]
        #     if isinstance(child, _Text):
        #         child.text = NEWLINE.sub('', child.text)
        raise NotImplementedError('sorry, yet to find an elegant way to remove newlines.')

    def render_children(self, context, children=None):
        if children is None:
            children = self.children

        def render_child(child):
            child_html = child.render(context)
            return '' if not child_html else str(child_html)

        return ''.join(map(render_child, children))


class _ScopableNode(_Node):
    creates_scope = True

    def save_end(self, frag):
        self.end_node = frag


class _Root(_Node):
    def render(self, context):
        return self.render_children(context)


class _Extends(_Node):
    def process_fragment(self, fragment):
        pass

    def render(self, context):
        pass


class _Block(_ScopableNode):
    def process_fragment(self, fragment):
        self.block_name = fragment.split()[1]

    def render(self, context):
        if self.end_node.clean != 'endblock':
            raise TemplateError('"%s" was found, but "endblock" is missing.' % self.frag)
        pass


class _Include(_Node):
    def process_fragment(self, fragment):
        # filename = fragment.split()[1]
        # self.filepath = os.path.join(os.getcwd(), filename)
        self.filepath = '/path/to/file'

    def render(self, context):
        with open(self.filepath) as f:
            contents = f.read()
            tpl = MiniTemplate(contents)

        return tpl.root.render(context)


class _Text(_Node):
    def process_fragment(self, fragment):
        self.text = fragment

    def render(self, context):
        return self.text


class _Variable(_Node):
    def process_fragment(self, fragment):
        self.has_filter = False
        bits = fragment.split('|')
        self.var = bits[0].strip()
        if len(bits) > 1:
            self.has_filter = True
            self.resolve_filter(bits)

    def resolve_filter(self, bits):
        bracket_reg = re.compile(r'(\(.*\))')
        self.callbacks = []
        funcs = map(do_trim, bits[1:])
        for func in funcs:
            args, kwargs = [], {}
            re_list = bracket_reg.split(func)
            has_param = True if len(re_list) > 1 else False
            if has_param:
                params = re_list[1][1:-1]
                if params:
                    param_list = params.split(',')
                    for it in param_list:
                        if '=' in it:
                            ls, rs = it.split('=')
                            kwargs[ls.strip()] = literal_eval(rs.strip())
                        else:
                            args.append(literal_eval(it))

            self.callbacks.append([re_list[0], args, kwargs])

    def render(self, context):
        # The variable safe-flag is used to check whether the filter:safe exists in the filter list.
        # Escape should always happen at the last second of rendering,
        # because type of raw value does not necessarily be str.
        safe_flag = []
        try:
            raw_value = eval(self.var, context, {})
            value = raw_value
        except:
            value = None

        if not self.has_filter:
            return value if context.get('~>_<~', '') == 'off' else html_escape(value)
        else:
            for it in self.callbacks:
                callback_name, args, kwargs = it[0], it[1], it[2]
                if callback_name == 'safe':
                    safe_flag.append(1)
                try:
                    callback = FILTERS[callback_name]
                    value = callback(value, *args, **kwargs)
                except:
                    raise TemplateFilterError(callback_name)

            if safe_flag or context.get('~>_<~', '') == 'off':
                return value
            else:
                return html_escape(value)


class _Comment(_Node):
    def render(self, context):
        return ''


class _Escape(_ScopableNode):
    def process_fragment(self, fragment):
        try:
            self.direc = fragment.split()[1]
        except:
            raise TemplateSyntaxError(fragment)
        if self.direc not in ['on', 'off', 'ON', 'OFF']:
            raise TemplateSyntaxError(fragment)

    def render(self, context):
        if self.end_node.clean != 'endescape':
            raise TemplateError('"%s" was found, but "endescape" is missing.' % self.frag)

        if self.direc in ['off', 'OFF']:
            new_dict = {'~>_<~': 'off'}
            esc_context = context.copy()
            esc_context.update(new_dict)
            return self.render_children(esc_context)
        return self.render_children(context)


class _Set(_ScopableNode):

    def process_fragment(self, fragment):
        try:
            and_reg = re.compile(r'\s*and\s*')
            _, expr = WHITESPACE.split(fragment, 1)
            self.args = and_reg.split(expr)
        except:
            raise TemplateSyntaxError(fragment)

    def render(self, context):
        if self.end_node.clean != 'endset':
            raise TemplateError('"%s" was found, but "endset" is missing.' % self.frag)

        new_context = {}
        for arg in self.args:
            n, v = arg.split('=')
            value = eval(v, context, {})
            new_dict = eval('dict(%s=value,)' % n, {'value': value}, {})
            new_context.update(new_dict)

        set_context = context.copy()
        set_context.update(new_context)
        return self.render_children(set_context)


class _For(_ScopableNode):
    def process_fragment(self, fragment):

        bits = WHITESPACE.split(fragment)
        try:
            self.loop_var = bits[1]
            self.raw_expr = bits[3]
        except:
            raise TemplateSyntaxError(fragment)

    def render(self, context):
        if self.end_node.clean != 'endfor':
            raise TemplateError('"%s" was found, but "endfor" is missing.' % self.frag)

        items = eval(self.raw_expr, context, {})

        loop_attr = {'length': len(items), 'index': 0, 'first': False, 'last': False}
        loop = type('_Loop', (), loop_attr)

        main_branch, empty_branch = self.branches[0], self.branches[1]

        def render_item(item):
            inner_context = context.copy()
            inner_context.update({self.loop_var: item, 'loop': loop})
            return self.render_children(inner_context)

        self.children = main_branch
        if not items and empty_branch:
            return self.render_children(context, empty_branch)

        loop_children = []

        for i, it in enumerate(items):
            loop.index = i + 1
            loop.first = True if i == 0 else False
            loop.last = True if i == loop.length - 1 else False
            loop_children.append(render_item(it))

        return ''.join(loop_children)

    def exit_scope(self):
        self.branches = self.split_children()

    def split_children(self):
        if _Empty not in map(type, self.children):
            return [self.children, []]

        main_branch, empty_branch = [], []
        current_branch = main_branch
        for child in self.children:
            if isinstance(child, _Empty):
                current_branch = empty_branch
                continue
            current_branch.append(child)
        return [main_branch, empty_branch]


class _Empty(_Node):
    def render(self, context):
        pass


class _If(_ScopableNode):
    def process_fragment(self, fragment):
        try:
            self.expr = fragment.split()[1]
        except:
            raise TemplateSyntaxError(fragment)

    def render(self, context):
        if self.end_node.clean != 'endif':
            raise TemplateError('"%s" was found, but "endif" is missing.' % self.frag)

        for branch in self.branches:
            con_bit = eval(branch[0], context, {})
            if con_bit:
                return self.render_children(context, branch[1])

    def exit_scope(self):
        self.branches = self.split_children()

    def split_children(self):
        """
        branches:
        a list that stores expr-branch pairs: [[if-expr,if-branch],[elif-expr,elif-branch],...[else-expr,else-branch]]
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
        try:
            self.expr = fragment.split()[1]
        except:
            raise TemplateSyntaxError(fragment)

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
        if self.end_node.clean != 'endraw':
            raise TemplateError('"%s" was found, but "endraw" is missing.' % self.frag)
        return ''.join(self.children)


class _Call(_Node):
    def process_fragment(self, fragment):
        try:
            bits = WHITESPACE.split(fragment, 1)
            self.func = bits[1]
        except (ValueError, IndexError):
            raise TemplateSyntaxError(fragment)

    def render(self, context):
        return eval(self.func, context, {})


class Compiler:
    def __init__(self, template_string):
        self.template_string = template_string

    def pre_compile(self, template_string):
        raise NotImplementedError('please wait~')

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
                if isinstance(parent_scope, _Raw) and fragment.clean != 'endraw':
                    parent_scope.children.append(fragment.raw)
                    continue
                else:
                    parent_scope.save_end(fragment)
                    parent_scope.exit_scope()
                    scope_stack.pop()
                    continue

            new_node = self.create_node(fragment)
            if new_node:
                if isinstance(parent_scope, _Raw):
                    parent_scope.children.append(fragment.raw)
                    continue
                else:
                    parent_scope.children.append(new_node)

                if new_node.creates_scope:
                    scope_stack.append(new_node)
                    new_node.enter_scope()
        return root

    @staticmethod
    def create_node(fragment):
        node_class = None
        if fragment.type == TEXT_FRAGMENT:
            node_class = _Text
        elif fragment.type == VAR_FRAGMENT:
            node_class = _Variable
        elif fragment.type == COMMENT_FRAGMENT:
            node_class = _Comment
        elif fragment.type == OPEN_BLOCK_FRAGMENT:
            cmd = fragment.clean.split()[0]
            if cmd == 'extends':
                node_class = _Extends
            elif cmd == 'block':
                node_class = _Block
            elif cmd == 'include':
                node_class = _Include
            elif cmd == 'for':
                node_class = _For
            elif cmd == 'empty':
                node_class = _Empty
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
            elif cmd == 'escape':
                node_class = _Escape
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

    # The injected context will be replaced by the local context.
    @classmethod
    def inject_context(cls, name, value):
        if not isinstance(name, str):
            raise Exception("<class 'str'> expected, but type of %s is %s." % (name, type(name)))
        cls.global_context[name] = value

    @staticmethod
    def add_filter(name, callback):
        if not isinstance(name, str):
            raise Exception("Filter-<%s> name should be a str." % str(callback))
        FILTERS[name] = callback

    def render(self, **kwargs):
        merged_kwargs = self.global_context.copy()
        merged_kwargs.update(kwargs)
        return self.root.render(merged_kwargs)


# utils
def html_escape(s):
    """ Escape HTML special characters ``&<>`` and quotes ``'"``. """
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')\
        .replace('"', '&quot;').replace("'", '&#039;')


def literal_eval(expr):
    try:
        return ast.literal_eval(expr)
    except ValueError:
        return expr


################################
# the following are the filters:
################################

### strings ###
def do_unescape(s):
    return str(s).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')\
        .replace('&quot;', '"').replace('&#039;', "'")


def do_trim(s):
    return str(s).strip()


def do_capitalize(s):
    return str(s).capitalize()


def do_upper(s):
    return str(s).upper()


def do_lower(s):
    return str(s).lower()


def do_truncate(s, length=255, end='...'):
    if len(s) <= length:
        return s

    result = s[:length-len(end)].rsplit(' ', 1)[0]
    if len(result) < length:
        result += ''
    return result + end


def do_wordcount(s):
    _word_re = re.compile(r'\w+(?u)')
    return len(_word_re.split(s))


### lists ###
def select_first(value):
    try:
        return value[0]
    except IndexError:
        return ''


def select_last(value):
    try:
        return value[-1]
    except IndexError:
        return ''


def get_length(value):
    try:
        return len(value)
    except (ValueError, TypeError):
        return 0


### integers ###
def do_round(value, precision=0, method='common'):
    if not method in ('common', 'ceil', 'floor'):
        raise Exception('error in round(filter) argument, method must be common, cel or floor.')
    if method == 'common':
        return round(value, precision)
    func = getattr(math, method)
    return func(value * (10 ** precision)) / (10 ** precision)


### dates ###
def format_date(value, arg=None):
    pass


def format_time(value, arg=None):
    pass


def time_since(value, arg=None):
    pass


def time_until(value, arg=None):
    pass


### logic ###
def set_default(value, arg):
    return value or arg


FILTERS = {
    'safe': do_unescape,
    'trim': do_trim,
    'capitalize': do_capitalize,
    'upper': do_upper,
    'lower': do_lower,
    'truncate': do_truncate,
    'wordcount': do_wordcount,
    'round': do_round,
    'first': select_first,
    'last': select_last,
    'length': get_length,
    'date': format_date,
    'time': format_time,
    'timesince': time_since,
    'timeuntil': time_until,
    'default': set_default
}

if __name__ == '__main__':

    cymoo = 'wake up, let us go home'
    num = 13.2436
    motto = '醒醒我们回家了'
    var = '1024*1024'

    persons = ['<cymoo>', 'colleen', 'ice', 'milkyway']

    raw = r"""
    {% set colleen='world is my idea' %}
    {% raw %}
    {% for item in persons %}
    {{ item }}
    {% endfor %}
    {{ colleen }}
    {% endraw %}
    {% for item in persons%}
    {{ item  }}
    {% endfor%}
    {{ colleen }}
    {% endset %}
    """
    import time
    t1 = time.time()
    frags = TOK_REGEX.split(raw)
    template = MiniTemplate(raw)
    html = template.render(persons=persons, cymoo=cymoo, num=num, motto=motto, var=var)
    t2 = time.time()
    print(html)
    print(t2-t1)