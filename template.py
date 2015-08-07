import re
import math
import ast
from random import choice

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

RAW_NODE_END = 'endraw'


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

    def __init__(self, ins, fragment=None):
        self.ins = ins
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


class _ScopeNode(_Node):
    creates_scope = True

    def save_end(self, frag):
        self.end_node = frag


class _Root(_Node):
    def render(self, context):
        children = self.children

        if isinstance(children[0], _Extends):
            _extends = children.pop(0)
            self.ins.block_dicts.append({})
            self.ins.has_ancestor = True
        elif isinstance(children[0], _Text) and isinstance(children[1], _Extends):
            _extends = children.pop(1)
            self.ins.block_dicts.append({})
            self.ins.has_ancestor = True
        else:
            _extends = None
            self.ins.has_ancestor = False

        if self.ins.has_ancestor:
            for child in self.children:
                if isinstance(child, _Block):
                    child.render(context)
            return _extends.render(context)
        else:
            return self.render_children(context)


#test
class _Extends(_Node):
    def process_fragment(self, fragment):
        filename = fragment.split()[1]

    def render(self, context):

        string = r"""
        <html>
        <head><title>wake up</title></head>
        <body>
            <header>This is the header.</header>
            {% block css %}css files{% endblock %}
            {% block content %}lorem{% endblock %}
            {% block script %}script files{% endblock %}
            <footer>This is the footer.{% block sub-content %}sub-lorem{% endblock %}</footer>
        </body>
        </html>
        """

        compiler = self.ins.compiler
        compiler.add_content(string)
        root = compiler.compile()
        return root.render(context)


#test
class _Block(_ScopeNode):
    def process_fragment(self, fragment):
        self.block_name = fragment.split()[1]

    def render(self, context):
        if self.end_node.clean != 'endblock':
            raise TemplateError('"To match "%s", "endblock" is expected, but "%s" was found.' %
                                (self.frag, self.end_node.clean))

        if self.ins.has_ancestor:
            result = self.render_children(context)
            self.ins.block_dicts[-1].update({self.block_name: result})
            return result
        else:
            for bd in reversed(self.ins.block_dicts):
                result = bd.get(self.block_name, '')
                if result:
                    return result
            return self.render_children(context)


class _Include(_Node):
    def process_fragment(self, fragment):
        # filename = fragment.split()[1]
        # self.filepath = os.path.join(os.getcwd(), filename)
        self.filepath = '/path/to/file'

    def render(self, context):
        # with open(self.filepath) as f:
        #     contents = f.read()
        #     tpl = MiniTemplate(contents)
        #
        # return tpl.root.render(context)
        pass


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


class _Escape(_ScopeNode):
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


class _Set(_ScopeNode):

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


class _For(_ScopeNode):
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


class _If(_ScopeNode):
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


class _Raw(_ScopeNode):
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
    def __init__(self, ins):
        self.ins = ins

    def add_content(self, template_string):
        self.template_string = template_string

    def each_fragment(self):
        for fragment in TOK_REGEX.split(self.template_string):
            if fragment:
                yield _Fragment(fragment)

    def compile(self):
        root = _Root(self.ins)
        scope_stack = [root]
        for fragment in self.each_fragment():
            if not scope_stack:
                raise TemplateError('nesting issues')
            parent_scope = scope_stack[-1]
            if fragment.type == CLOSE_BLOCK_FRAGMENT:
                if isinstance(parent_scope, _Raw) and fragment.clean != RAW_NODE_END:
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
        return node_class(self.ins, fragment.clean)


class MiniTemplate:
    global_context = {}

    def __init__(self, contents=None):
        self.has_ancestor = False
        self.block_dicts = []
        # self.ancestor_stack = []
        self.compiler = Compiler(self)
        self.compiler.add_content(contents)
        self.root = self.compiler.compile()

    @classmethod
    def inject_context(cls, name, value):
        """
        Inject the global context to the template, and the context will be shared by all instances.
        The variables which have the same name with ones in the local context will be substituted.
        """
        if not isinstance(name, str):
            raise Exception("<class 'str'> expected, but type of %s is %s." % (name, type(name)))
        cls.global_context[name] = value

    @staticmethod
    def add_filter(name, callback):
        """
        Add a filter to the template; a filter is used to alter the original value.
        Filter function should not do complex logic.
        """
        if not isinstance(name, str):
            raise Exception("Filter-<%s> name should be a str." % str(callback))
        FILTERS[name] = callback

    def render(self, **kwargs):
        self.merged_kwargs = self.global_context.copy()
        self.merged_kwargs.update(kwargs)
        result = self.root.render(self.merged_kwargs)
        print('block-dicts', self.block_dicts)
        return result


# utils
def html_escape(s):
    """ Escape HTML special characters ``&<>`` and quotes ``'"``. """
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')\
        .replace('"', '&quot;').replace("'", '&#039;')


def literal_eval(expr):
    """
    ast.literal_eval is used to safely evaluate a string and return a basic type value:
    str, int, float, True/False, None, dict, list, tuple.
    Always use literal_eval instead of eval when possible.
    """
    try:
        return ast.literal_eval(expr)
    except ValueError:
        return expr


################################
# the following are the filters:
################################

### strings ###
def do_unescape(s):
    """Unescape HTML special characters."""
    return str(s).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')\
        .replace('&quot;', '"').replace('&#039;', "'")


def do_trim(s):
    """Strip leading and trailing whitespace."""
    return str(s).strip()


def do_capitalize(s):
    """Capitalize a value. The first character will be uppercase, all others lowercase."""
    return str(s).capitalize()


def do_upper(s):
    """Convert a value to uppercase."""
    return str(s).upper()


def do_lower(s):
    """Convert a value to lowercase."""
    return str(s).lower()


def do_truncate(s, length=255, end='...'):
    """
    Return a truncated copy of the string. The length is specified with the first
    parameter which defaults to 255. If the text was in fact truncated it will append
    an ellipsis sign "...". If you want a different ellipsis sign than "..." you can
    specify it using the last parameter.
    """
    if len(s) <= length:
        return s

    result = s[:length-len(end)].rsplit(' ', 1)[0]
    if len(result) < length:
        result += ''
    return result + end


def do_wordcount(s):
    """Count the words in that string. """
    _word_re = re.compile(r'\w+(?u)')
    return len(_word_re.split(s))


### lists ###
def select_first(seq):
    """Return the first item of a sequence."""
    try:
        return next(iter(seq))
    except StopIteration:
        return 'No first item, sequence was empty.'


def select_last(seq):
    """Return the last item of a sequence."""
    try:
        return next(iter(reversed(seq)))
    except StopIteration:
        return 'No first item, sequence was empty.'


def select_random(seq):
    """Return a random item from that sequence."""
    try:
        return choice(seq)
    except IndexError:
        return 'No random item, sequence was empty.'


def get_length(seq):
    """Return the length of a sequence."""
    try:
        return len(seq)
    except (ValueError, TypeError):
        return 0


### numbers ###
def do_round(value, precision=0, method='common'):
    """
    Round the number to a given precision. The first parameter specifies the precision,
    the second the rounding method.
    """
    if not method in ('common', 'ceil', 'floor'):
        raise Exception('error in round(filter) argument, method must be common, cel or floor.')
    if method == 'common':
        return round(value, precision)
    func = getattr(math, method)
    return func(value * (10 ** precision)) / (10 ** precision)


def do_int(value, default=0):
    """
    Convert the value into an integer. If the conversion doesn't work it will return 0.
    You can override the default using the first parameter.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def do_float(value, default=0.0):
    """
    Convert the value into an float. If the conversion doesn't work it will return 0.0.
    You can override the default using the first parameter.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    """If the value is undefined, it will return the passed default value."""
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
    'int': do_int,
    'float': do_float,
    'first': select_first,
    'last': select_last,
    'random': select_random,
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
    {% extends test %}
    {% block content %}{{ motto }}{% endblock %}
    {% block sub-content %}{{ cymoo }}{% endblock %}
    """

    frags = TOK_REGEX.split(raw)
    template = MiniTemplate(raw)
    html = template.render(persons=persons, cymoo=cymoo, num=num, motto=motto, var=var)
    print(html)