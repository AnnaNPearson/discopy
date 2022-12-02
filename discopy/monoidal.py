# -*- coding: utf-8 -*-

"""
The free (pre)monoidal category, i.e. planar diagrams.

Summary
-------

.. autosummary::
    :template: class.rst
    :nosignatures:
    :toctree:

    Ty
    PRO
    Layer
    Diagram
    Box
    Sum
    Bubble
    Category
    Functor
    Whiskerable

Axioms
------
We can check the axioms for :class:`Ty` being a monoid.

>>> x, y, z, unit = Ty('x'), Ty('y'), Ty('z'), Ty()
>>> assert x @ unit == x == unit @ x
>>> assert (x @ y) @ z == x @ y @ z == x @ (y @ z)

We can check the axioms for dagger monoidal categories, up to interchanger.

>>> x, y, z, w = Ty('x'), Ty('y'), Ty('z'), Ty('w')
>>> f0, f1 = Box('f0', x, y), Box('f1', z, w)
>>> d = Id(x) @ f1 >> f0 @ Id(w)
>>> assert d == (f0 @ f1).interchange(0, 1)
>>> assert f0 @ f1 == d.interchange(0, 1)
>>> assert (f0 @ f1)[::-1][::-1] == f0 @ f1
>>> assert (f0 @ f1)[::-1].interchange(0, 1) == f0[::-1] @ f1[::-1]

We can check the Eckmann-Hilton argument, up to interchanger.

>>> s0, s1 = Box('s0', Ty(), Ty()), Box('s1', Ty(), Ty())
>>> assert s0 @ s1 == s0 >> s1 == (s1 @ s0).interchange(0, 1)
>>> assert s1 @ s0 == s1 >> s0 == (s0 @ s1).interchange(0, 1)

.. image:: /imgs/EckmannHilton.gif
    :align: center
"""

from __future__ import annotations
from dataclasses import dataclass
from abc import ABC, abstractmethod

from discopy import cat, drawing, rewriting, messages
from discopy.cat import factory, Ob, assert_iscomposable
from discopy.messages import WarnOnce
from discopy.utils import factory_name, from_tree, assert_isinstance


@factory
class Ty(cat.Ob):
    """
    A type is a tuple of objects with :meth:`Ty.tensor` as concatenation.

    Parameters:
        inside : The objects inside the type (or their names).

    Tip
    ---
    Types can be instantiated with a name rather than object.

    >>> assert Ty('x') == Ty(cat.Ob('x'))

    Tip
    ---
    Types can be indexed and sliced like ordinary Python lists.

    >>> t = Ty('x', 'y', 'z')
    >>> assert t[0] == t[:1] == Ty('x')
    >>> assert t[1:] == t[-2:] == Ty('y', 'z')

    Tip
    ---
    A type can be exponentiated by a natural number.

    >>> assert Ty('x') ** 3 == Ty('x', 'x', 'x')
    """
    ob_factory = cat.Ob

    __ambiguous_inheritance__ = True

    def __init__(self, *inside: str | cat.Ob):
        for obj in inside:
            assert_isinstance(obj, (str, self.ob_factory))
        self.inside = tuple(
            self.ob_factory(x) if isinstance(x, str) else x for x in inside)
        super().__init__(str(self))

    def tensor(self, *others: Ty) -> Ty:
        """
        Returns the tensor of types, i.e. the concatenation of their lists
        of objects. This is called with the binary operator :code:`@`.

        Parameters:
            others : The other types to tensor.

        Tip
        ---
        A list of types can be tensored by calling :code:`Ty().tensor`.

        >>> list_of_types = [Ty('x'), Ty('y'), Ty('z')]
        >>> assert Ty().tensor(*list_of_types) == Ty('x', 'y', 'z')
        """
        for other in others:
            assert_isinstance(self, other.factory)
            assert_isinstance(other, self.factory)
        inside = self.inside + tuple(x for t in others for x in t.inside)
        return self.factory(*inside)

    def count(self, obj: cat.Ob) -> int:
        """
        Counts the occurrence of a given object (or a type of length 1).

        Parameters:
            obj : The object to count.

        Example
        -------

        >>> x = Ty('x')
        >>> xs = x ** 5
        >>> assert xs.count(x) == xs.inside.count(x.inside[0])
        """
        obj, = obj.inside if isinstance(obj, Ty) else (obj, )
        return self.inside.count(obj)

    def drawing(self) -> Ty:
        """ Called before :meth:`Diagram.draw`. """
        return Ty(*map(str, self.inside))

    @property
    def is_atomic(self) -> bool:
        """ Whether a type is atomic, i.e. it has length 1. """
        return len(self) == 1

    def __eq__(self, other):
        return isinstance(other, Ty) and self.inside == other.inside

    def __hash__(self):
        return hash(repr(self))

    def __repr__(self):
        return factory_name(type(self)) + "({})".format(
            ', '.join(map(repr, self.inside)))

    def __str__(self):
        return ' @ '.join(map(str, self.inside)) or type(self).__name__ + '()'

    def __len__(self):
        return len(self.inside)

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.factory(*self.inside[key])
        return cat.Arrow.__getitem__(self, key)

    def __pow__(self, n_times):
        return self.factory().tensor(*n_times * [self])

    def to_tree(self):
        return {
            'factory': factory_name(type(self)),
            'inside': [x.to_tree() for x in self.inside]}

    @classmethod
    def from_tree(cls, tree):
        return cls(*map(from_tree, tree['inside']))

    def __matmul__(self, other):
        return self.tensor(other) if isinstance(other, Ty) else NotImplemented

    __add__ = __matmul__


@factory
class PRO(Ty):
    """
    A PRO is a natural number ``n`` seen as a type with unnamed objects.

    Parameters
    ----------
    n : int
        The length of the PRO type.

    Examples
    --------
    >>> assert PRO(1) @ PRO(1) == PRO(2)
    >>> assert PRO(42).inside == 42 * (Ob(), )
    """
    def __init__(self, n: int = 0):
        self.n = n

    @property
    def inside(self):
        return self.n * (Ob(), )

    def tensor(self, *others: PRO) -> PRO:
        for other in others:
            if not isinstance(other, Ty):
                return NotImplemented  # This allows whiskering on the left.
            assert_isinstance(self, other.factory)
            assert_isinstance(other, self.factory)
        return self.factory(self.n + sum(other.n for other in others))

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.factory(len(self.inside[key]))
        return cat.Arrow.__getitem__(self, key)

    def __len__(self):
        return self.n

    def __repr__(self):
        return factory_name(type(self)) + "({})".format(len(self))

    def __str__(self):
        return f"PRO({str(self.n)})"

    def __eq__(self, other):
        return isinstance(other, self.factory) and self.n == other.n

    def __hash__(self):
        return hash(repr(self))

    def __pow__(self, n_times):
        return self.factory(n_times * self.n)

    def drawing(self):
        return Ty(*self.n * [Ob()])

    def to_tree(self):
        return {'factory': factory_name(type(self)), 'n': self.n}

    @classmethod
    def from_tree(cls, tree):
        return cls(tree['n'])


class Layer(cat.Box):
    """
    A layer is a :code:`box` in the middle of a pair of types
    :code:`left` and :code:`right`.

    Parameters:
        left : The type on the left of the layer.
        box : The box in the middle of the layer.
        right : The type on the right of the layer.
        more : More boxes and types to the right,
               used by :meth:`Diagram.foliation`.
    """
    def __init__(self, left: Ty, box: Box, right: Ty, *more):
        if len(more) % 2:
            raise ValueError(messages.LAYERS_MUST_BE_ODD)
        self.boxes_or_types = (left, box, right) + more
        name, dom, cod = "", left[:0], left[:0]
        for i, box_or_typ in enumerate(self.boxes_or_types):
            if i % 2:
                assert_isinstance(box, Box)
                dom, cod = dom @ box_or_typ.dom, cod @ box_or_typ.cod
                name += ("" if not name else " @ ") + str(box_or_typ)
            else:
                assert_isinstance(box_or_typ, Ty)
                dom, cod = dom @ box_or_typ, cod @ box_or_typ
                name += "" if not box_or_typ\
                    else ("" if not name else " @ ") + str(box_or_typ)
        super().__init__(name, dom, cod)

    def __iter__(self):
        for box_or_typ in self.boxes_or_types:
            yield box_or_typ

    def __eq__(self, other):
        return isinstance(other, Layer) and tuple(self) == tuple(other)

    def __repr__(self):
        return factory_name(type(self))\
            + "({})".format(", ".join(map(repr, self)))

    def __matmul__(self, other: Ty) -> Layer:
        *tail, head = self
        boxes_and_types = tail + (
            [head @ other] if isinstance(other, Ty)
            else [head, other.dom[:0], other])
        return type(self)(*boxes_and_types)

    def __rmatmul__(self, other: Ty) -> Layer:
        head, *tail = self
        return type(self)(other @ head, *tail)

    @classmethod
    def cast(cls, box: Box) -> Layer:
        """
        Turns a box into a layer with empty types on the left and right.

        Parameters:
            box : The box in the middle of empty types.

        Example
        -------
        >>> f = Box('f', Ty('x'), Ty('y'))
        >>> assert Layer.cast(f) == Layer(Ty(), f, Ty())
        """
        return cls(box.dom[:0], box, box.dom[len(box.dom):])

    def dagger(self) -> Layer:
        return type(self)(*(
            x.dagger() if i % 2 else x for i, x in enumerate(self)))

    def drawing(self) -> Diagram:
        """ Called before :meth:`Diagram.draw`. """
        result = Ty()
        for box_or_typ in self:
            result = result @ box_or_typ.drawing()
        return result

    @property
    def boxes_and_offsets(self) -> list[tuple[Box, int]]:
        """
        The offsets of each box inside the layer.

        Example
        -------
        >>> a, b, c, d, e = map(Ty, "abcde")
        >>> f, g = Box('f', a, b), Box('g', c, d)
        >>> assert Layer(e, f, e, g, e).boxes_and_offsets == [(f, 1), (g, 3)]
        """
        left, box, *tail = self
        boxes, offsets = [box], [len(left)]
        for typ, box in zip(tail[::2], tail[1::2]):
            boxes.append(box)
            offsets.append(offsets[-1] + len(boxes[-1].dom) + len(typ))
        return list(zip(boxes, offsets))

    def merge(self, other: Layer) -> Layer:
        """
        Merge two layers into one or raise :class:`AxiomError`,
        used by :meth:`Diagram.foliation`.

        Parameters:
            other : The other layer with which to merge.

        Example
        -------
        >>> a, b, c, d, e = map(Ty, "abcde")
        >>> f, g = Box('f', a, b), Box('g', c, d)
        >>> layer0 = Layer(e,  f,  e @ c @ e)
        >>> layer1 = Layer(e @ b @ e,  g,  e)
        >>> assert layer0.merge(layer1) == Layer(e, f, e, g, e)
        """
        assert_iscomposable(self, other)
        scan, boxes_or_types = 0, []
        for box, offset in sorted(
                self.boxes_and_offsets + other.boxes_and_offsets,
                key=lambda x: x[1]):
            if scan > offset:
                raise cat.AxiomError(
                    messages.NOT_MERGEABLE.format(self, other))
            boxes_or_types.append(self.dom[scan:offset])
            boxes_or_types.append(box)
            scan = offset + len(box.dom)
        boxes_or_types.append(self.dom[scan:])
        return type(self)(*boxes_or_types)

    def lambdify(self, *symbols, **kwargs):
        left, box, right = self
        return lambda *xs: left @ box.lambdify(*symbols, **kwargs)(*xs) @ right

    def to_tree(self) -> dict:
        return dict(factory=factory_name(type(self)),
                    inside=[x.to_tree() for x in self])

    @classmethod
    def from_tree(cls, tree: dict) -> Layer:
        return cls(*(map(from_tree, tree['inside'])))


class Whiskerable(ABC):
    """
    Abstract class implementing the syntactic sugar :code:`@` for whiskering
    and parallel composition with some method :code:`tensor`.
    """
    @classmethod
    @abstractmethod
    def id(cls, dom: any) -> Whiskerable:
        """
        Identity on a given domain, to be instantiated.

        Parameters:
            dom : The object on which to take the identity.
        """

    @abstractmethod
    def tensor(self, other: Whiskerable) -> Whiskerable:
        """
        Parallel composition, to be instantiated.

        Parameters:
            other : The other diagram to compose in parallel.
        """

    @classmethod
    def whisker(cls, other: any) -> Whiskerable:
        """
        Apply :meth:`Whiskerable.id` if :code:`other` is not tensorable else do
        nothing.

        Parameters:
            other : The whiskering object.
        """
        return other if isinstance(other, Whiskerable) else cls.id(other)

    __matmul__ = lambda self, other: self.tensor(self.whisker(other))
    __rmatmul__ = lambda self, other: self.whisker(other).tensor(self)


@factory
class Diagram(cat.Arrow, Whiskerable):
    """
    A diagram is a tuple of composable layers :code:`inside` with a pair of
    types :code:`dom` and :code:`cod` as domain and codomain.

    Parameters:
        inside : The layers of the diagram.
        dom : The domain of the diagram, i.e. its input.
        cod : The codomain of the diagram, i.e. its output.

    .. admonition:: Summary

        .. autosummary::

            tensor
            boxes
            offsets
            draw
            interchange
            normalize
            normal_form
    """
    ty_factory = Ty
    layer_factory = Layer

    def __init__(
            self, inside: tuple[Layer, ...], dom: Ty, cod: Ty, _scan=True):
        for layer in inside:
            assert_isinstance(layer, Layer)
        super().__init__(inside, dom, cod, _scan=_scan)

    def tensor(self, other: Diagram = None, *others: Diagram) -> Diagram:
        """
        Parallel composition, called using :code:`@`.

        Parameters:
            other : The other diagram to tensor.
            rest : More diagrams to tensor.

        Important
        ---------
        The definition of tensor is biased to the left, i.e.::

            self @ other == self @ other.dom >> self.cod @ other

        Example
        -------
        >>> x, y, z, w = Ty('x'), Ty('y'), Ty('z'), Ty('w')
        >>> f0, f1 = Box('f0', x, y), Box('f1', z, w)
        >>> assert f0 @ f1 == f0.tensor(f1) == f0 @ Id(z) >> Id(y) @ f1

        >>> (f0 @ f1).draw(
        ...     figsize=(2, 2),
        ...     path='docs/imgs/monoidal/tensor-example.png')

        .. image:: /imgs/monoidal/tensor-example.png
            :align: center
        """
        if other is None:
            return self
        if others:
            return self.tensor(other).tensor(*others)
        if isinstance(other, Sum):
            return self.sum_factory([self]).tensor(other)
        assert_isinstance(other, self.factory)
        assert_isinstance(self, other.factory)
        if isinstance(other, Sum):
            self.sum_factory.cast(self).tensor(other)
        inside = tuple(layer @ other.dom for layer in self.inside)\
            + tuple(self.cod @ layer for layer in other.inside)
        dom, cod = self.dom @ other.dom, self.cod @ other.cod
        return self.factory(inside, dom, cod)

    @property
    def boxes(self) -> list[Box]:
        """ The boxes in each layer of the diagram. """
        return list(box for _, box, _ in self)

    @property
    def offsets(self) -> list[int]:
        """ The offset of a box is the length of the type on its left. """
        return list(len(left) for left, _, _ in self)

    @property
    def width(self):
        """
        The width of a diagram, i.e. the maximum number of parallel wires.

        Example
        -------
        >>> x = Ty('x')
        >>> f = Box('f', x, x ** 4)
        >>> diagram = f @ x ** 2 >> x ** 2 @ f.dagger()
        >>> assert diagram.width == 6
        """
        return max(len(self.dom), max(len(layer.cod) for layer in self))

    def encode(self) -> tuple[Ty, list[tuple[Box, int]]]:
        """
        Compact encoding of a diagram as a tuple of boxes and offsets.

        Example
        -------
        >>> x, y, z, w = Ty('x'), Ty('y'), Ty('z'), Ty('w')
        >>> f0, f1, g = Box('f0', x, y), Box('f1', z, w), Box('g', y @ w, y)
        >>> diagram = f0 @ f1 >> g
        >>> dom, boxes_and_offsets = diagram.encode()
        >>> assert dom == x @ z
        >>> assert boxes_and_offsets == [(f0, 0), (f1, 1), (g, 0)]
        >>> assert diagram == Diagram.decode(*diagram.encode())
        >>> diagram.draw(figsize=(2, 2),
        ...        path='docs/imgs/monoidal/arrow-example.png')

        .. image:: /imgs/monoidal/arrow-example.png
            :align: center
        """
        return self.dom, list(zip(self.boxes, self.offsets))

    @classmethod
    def decode(cls, dom: Ty, boxes_and_offsets: list[tuple[Box, int]]
            ) -> Diagram:
        """
        Turn a tuple of boxes and offsets into a diagram.

        Parameters:
            dom : The domain of the diagram.
            boxes_and_offsets : The boxes and offsets of the diagram.
        """
        diagram = cls.id(dom)
        for box, offset in boxes_and_offsets:
            left = diagram.cod[:offset]
            right = diagram.cod[offset + len(box.dom):]
            diagram = diagram >> left @ box @ right
        return diagram

    def drawing(self):
        """ Called before :meth:`Diagram.draw`. """
        ob, ar = Ty.drawing, Layer.drawing
        return cat.Functor(ob, ar, cod=Category())(self)


class Box(cat.Box, Diagram):
    """
    A box is a diagram with a :code:`name` and the layer of just itself inside.

    Parameters:
        name : The name of the box.
        dom : The domain of the box, i.e. the input.
        cod : The codomain of the box, i.e. the output.
        data (any) : Extra data in the box, default is :code:`None`.
        is_dagger (bool, optional) : Whether the box is dagger.

    Other parameters
    ----------------

    draw_as_spider : bool, optional
        Whether to draw the box as a spider.
    draw_as_wires : bool, optional
        Whether to draw the box as wires, e.g. :class:`discopy.symmetric.Swap`.
    draw_as_braid : bool, optional
        Whether to draw the box as a a braid, e.g. :class:`braided.Braid`.
    drawing_name : str, optional
        The name to use when drawing the box.
    tikzstyle_name : str, optional
        The name of the style when tikzing the box.
    color : str, optional
        The color to use when drawing the box, one of
        :code:`"white", "red", "green", "blue", "yellow", "black"`.
        Default is :code:`"red" if draw_as_spider else "white"`.
    shape : str, optional
        The shape to use when drawing a spider,
        one of :code:`"circle", "rectangle"`.

    Examples
    --------
    >>> f = Box('f', Ty('x', 'y'), Ty('z'))
    >>> assert Id(Ty('x', 'y')) >> f == f == f >> Id(Ty('z'))
    >>> assert Id(Ty()) @ f == f == f @ Id(Ty())
    >>> assert f == f[::-1][::-1]
    """
    __ambiguous_inheritance__ = (cat.Box, )

    def drawing(self) -> Box:
        dom, cod = self.dom.drawing(), self.cod.drawing()
        result = Box(self.name, dom, cod, is_dagger=self.is_dagger)
        for attr, value in self.__dict__.items():
            if attr in drawing.ATTRIBUTES:
                setattr(result, attr, value)
        return result

    def __init__(self, name: str, dom: Ty, cod: Ty, **params):
        for attr in drawing.ATTRIBUTES:
            value = params.pop(attr, None)
            if value is not None:
                setattr(self, attr, value)
        cat.Box.__init__(self, name, dom, cod, **params)
        inside = (self.layer_factory.cast(self), )
        Diagram.__init__(self, inside, dom, cod)

    def __eq__(self, other):
        if isinstance(other, Box):
            return cat.Box.__eq__(self, other)
        return isinstance(other, Diagram)\
            and other.inside == (self.layer_factory.cast(self), )

    def __hash__(self):
        return hash(repr(self))


class Sum(cat.Sum, Box):
    """
    A sum is a tuple of diagrams :code:`terms`
    with the same domain and codomain.

    Parameters:
        terms (tuple[Diagram, ...]) : The terms of the formal sum.
        dom (Ty) : The domain of the formal sum.
        cod (Ty) : The codomain of the formal sum.
    """
    __ambiguous_inheritance__ = (cat.Sum, )

    def tensor(self, *others):
        if len(others) != 1:
            return super().tensor(*others)
        other, = others
        other = other if isinstance(other, Sum) else self.sum_factory((other, ))
        dom, cod = self.dom @ other.dom, self.cod @ other.cod
        terms = tuple(f.tensor(g) for f in self.terms for g in other.terms)
        return self.sum_factory(terms, dom, cod)

    def draw(self, **params):
        """ Drawing a sum as an equation with :code:`symbol='+'`. """
        return drawing.equation(*self.terms, symbol='+', **params)


class Bubble(cat.Bubble, Box):
    """
    A bubble is a box with a diagram :code:`arg` inside and an optional pair of
    types :code:`dom` and :code:`cod`.

    Parameters:
        arg : The diagram inside the bubble.
        dom : The domain of the bubble, default is that of :code:`other`.
        cod : The codomain of the bubble, default is that of :code:`other`.

    Examples
    --------
    >>> x, y = Ty('x'), Ty('y')
    >>> f, g = Box('f', x, y ** 3), Box('g', y, y @ y)
    >>> d = (f.bubble(dom=x @ x, cod=y) >> g).bubble()
    >>> d.draw(path='docs/imgs/monoidal/bubble-example.png')

    .. image:: /imgs/monoidal/bubble-example.png
        :align: center
    """
    __ambiguous_inheritance__ = (cat.Bubble, )

    def __init__(self, arg: Diagram, dom: Ty = None, cod: Ty = None, **params):
        self.drawing_name = params.get("drawing_name", "")
        cat.Bubble.__init__(self, arg, dom, cod)
        Box.__init__(self, self.name, self.dom, self.cod, data=self.data)

    def drawing(self):
        dom, cod = self.dom.drawing(), self.cod.drawing()
        argdom, argcod = self.arg.dom.drawing(), self.arg.cod.drawing()
        obj = cat.Ob(self.drawing_name)
        obj.draw_as_box = True
        left, right = Ty(obj), Ty("")
        _open = Box("_open", dom, left @ argdom @ right)
        _close = Box("_close", left @ argcod @ right, cod)
        _open.draw_as_wires = _close.draw_as_wires = True
        # Wires can go straight only if types have the same length.
        _open.bubble_opening = len(dom) == len(argdom)
        _close.bubble_closing = len(cod) == len(argcod)
        return _open >> left @ self.arg.drawing() @ right >> _close


class Category(cat.Category):
    """
    A monoidal category is a category with a method :code:`tensor`.

    Parameters:
        ob : The type of objects.
        ar : The type of arrows.
    """
    __ambiguous_inheritance__ = True

    ob, ar = Ty, Diagram


class Functor(cat.Functor):
    """
    A monoidal functor is a functor that preserves the tensor product.

    Parameters:
        ob (Mapping[Ty, Ty]) : Map from atomic :class:`Ty` to :code:`cod.ob`.
        ar (Mapping[Box, Diagram]) : Map from :class:`Box` to :code:`cod.ar`.
        cod (Category) : The codomain of the functor.

    Important
    ---------
    The keys of the objects mapping must be atomic types, i.e. of length 1.

    Example
    -------
    >>> x, y, z, w = Ty('x'), Ty('y'), Ty('z'), Ty('w')
    >>> f0, f1 = Box('f0', x, y, data=[0.1]), Box('f1', z, w, data=[1.1])
    >>> F = Functor({x: z, y: w, z: x, w: y}, {f0: f1, f1: f0})
    >>> assert F(f0) == f1 and F(f1) == f0
    >>> assert F(F(f0)) == f0
    >>> assert F(f0 @ f1) == f1 @ f0
    >>> assert F(f0 >> f0[::-1]) == f1 >> f1[::-1]
    >>> source, target = f0 >> f0[::-1], F(f0 >> f0[::-1])
    >>> drawing.equation(
    ...     source, target, symbol='$\\\\mapsto$', figsize=(4, 2),
    ...     path='docs/imgs/monoidal/functor-example.png')

    .. image:: /imgs/monoidal/functor-example.png
        :align: center
    """
    __ambiguous_inheritance__ = True

    dom = cod = Category(Ty, Diagram)

    def __call__(self, other):
        if isinstance(other, Ty):
            return sum(map(self, other.inside), self.cod.ob())
        if isinstance(other, cat.Ob):
            result = self.ob[self.dom.ob(other)]
            dtype = getattr(self.cod.ob, "__origin__", self.cod.ob)
            # Syntactic sugar {x: n} in tensor and {x: int} in python.
            return result if isinstance(result, dtype) else\
                (result, ) if dtype == tuple else self.cod.ob(result)
        if isinstance(other, Layer):
            head, *tail = other
            result = self(head)
            for box_or_typ in tail:
                result = result @ self(box_or_typ)
            return result
        return super().__call__(other)


def assert_isatomic(typ: Ty, cls: type = None):
    cls = cls or type(typ)
    assert_isinstance(typ, cls)
    if not typ.is_atomic:
        raise ValueError(messages.NOT_ATOMIC.format(
            factory_name(cls), len(typ)))


Diagram.draw = drawing.draw
Diagram.to_gif = drawing.to_gif
Diagram.interchange = rewriting.interchange
Diagram.normalize = rewriting.normalize
Diagram.normal_form = rewriting.normal_form
Diagram.foliation = rewriting.foliation
Diagram.depth = rewriting.depth

Diagram.sum_factory = Sum
Diagram.bubble_factory = Bubble
Id = Diagram.id
