# -*- coding: utf-8 -*-

"""
The monoidal category of classical-quantum circuits
with digits and qudits as objects.

Objects are :class:`Ty` generated by two basic types
:code:`bit` and :code:`qubit`.

Arrows are diagrams generated by :class:`QuantumGate`, :class:`ClassicalGate`,
:class:`Discard`, :class:`Measure` and :class:`Encode`.

Summary
-------

.. autosummary::
    :template: class.rst
    :nosignatures:
    :toctree:

    Ob
    Digit
    Qudit
    Ty
    Circuit
    Box
    Sum
    Swap
    Functor

.. admonition:: Functions

    .. autosummary::
        :template: function.rst
        :nosignatures:
        :toctree:

        index2bitstring
        bitstring2index

Examples
--------
>>> from discopy.quantum.gates import (
...     Ket, CX, H, X, Rz, sqrt, Controlled, Measure, Discard)
>>> circuit = Ket(0, 0) >> CX >> Controlled(Rz(0.25)) >> Measure() @ Discard()
>>> circuit.draw(
...     figsize=(3, 6),
...     path='docs/imgs/quantum/circuit-example.png')

.. image:: /imgs/quantum/circuit-example.png
    :align: center


>>> from discopy.grammar.pregroup import Word
>>> from discopy.rigid import Ty, Cup, Id
>>> s, n = Ty('s'), Ty('n')
>>> Alice = Word('Alice', n)
>>> loves = Word('loves', n.r @ s @ n.l)
>>> Bob = Word('Bob', n)
>>> grammar = Cup(n, n.r) @ Id(s) @ Cup(n.l, n)
>>> sentence = grammar << Alice @ loves @ Bob
>>> ob = {s: 0, n: 1}
>>> ar = {Alice: Ket(0),
...       loves: CX << sqrt(2) @ H @ X << Ket(0, 0),
...       Bob: Ket(1)}
>>> F = Functor(ob, ar)
>>> assert abs(F(sentence).eval().array) ** 2
>>> from discopy import drawing
>>> drawing.equation(
...     sentence, F(sentence), symbol='$\\\\mapsto$',
...     figsize=(6, 3), nodesize=.5,
...     path='docs/imgs/quantum/functor-example.png')

.. image:: /imgs/quantum/functor-example.png
    :align: center
"""

from __future__ import annotations

import random
from math import pi
from functools import reduce, partial
from itertools import takewhile, chain
from collections.abc import Mapping

from discopy import messages, monoidal, rigid, tensor, symmetric, frobenius
from discopy.cat import factory, Category, AxiomError
from discopy.compact import Diagram
from discopy.tensor import Dim, Tensor
from discopy.utils import factory_name, assert_isinstance

class Ob(frobenius.Ob):
    """
    Information units of some integer dimension greater than 1.

    Parameters:
        name : The name of the object, e.g. ``"bit"`` or ``"qubit"``.
        dim : The dimension of the object, e.g. ``2`` for bits and qubits.

    Examples
    --------
    >>> assert bit.inside == [Ob("bit", dim=2)]
    >>> assert qubit.inside == [Ob("qubit", dim=2)]
    """
    def __init__(self, name: str, dim=2, z=0):
        assert_isinstance(self, (Digit, Qudit))
        assert_isinstance(dim, int)
        if dim < 2:
            raise ValueError("Dimension should be an int greater than 1.")
        assert_isinstance(z, int)
        if z != 0:
            raise AxiomError("circuit.Ob are self-dual.")
        super().__init__(name)
        self.dim = dim

    def __repr__(self):
        return "{}({})".format(factory_name(type(self)), self.dim)


class Digit(Ob):
    """
    Classical unit of information of some dimension :code:`dim`.

    Parameters:
        dim : The dimension of the digit, e.g. ``2`` for bits.

    Examples
    --------
    >>> assert bit.inside == [Digit(2)] == [Ob("bit", dim=2)]
    """
    def __init__(self, dim: int, z=0):
        name = "bit" if dim == 2 else "Digit({})".format(dim)
        super().__init__(name, dim)


class Qudit(Ob):
    """
    Quantum unit of information of some dimension :code:`dim`.

    Parameters:
        dim : The dimension of the qudit, e.g. ``2`` for qubits.

    Examples
    --------
    >>> assert qubit.inside == [Qudit(2)] == [Ob("qubit", dim=2)]
    """
    def __init__(self, dim, z=0):
        name = "qubit" if dim == 2 else "Qudit({})".format(dim)
        super().__init__(name, dim)


@factory
class Ty(frobenius.Ty):
    """
    A circuit type is a frobenius type with :class:`Digit` and :class:`Qudit`
    objects inside.

    Examples
    --------
    >>> assert bit == Ty(Digit(2))
    >>> assert qubit == Ty(Qudit(2))
    >>> assert bit @ qubit != qubit @ bit

    You can construct :code:`n` qubits by taking powers of :code:`qubit`:

    >>> print(bit ** 2 @ qubit ** 3)
    bit @ bit @ qubit @ qubit @ qubit
    """
    ob_factory = Ob


@factory
class Circuit(tensor.Diagram):
    """ Classical-quantum circuits. """
    def conjugate(self):
        return self.l

    @property
    def is_mixed(self):
        """
        Whether the circuit is mixed, i.e. it contains both bits and qubits
        or it discards qubits. Mixed circuits can be evaluated only by a
        :class:`CQMapFunctor` not a :class:`discopy.tensor.Functor`.
        """
        both_bits_and_qubits = self.dom.count(bit) and self.dom.count(qubit)\
            or any(layer.cod.count(bit) and layer.cod.count(qubit)
                   for layer in self.layers)
        return both_bits_and_qubits or any(box.is_mixed for box in self.boxes)

    def init_and_discard(self):
        """ Returns a circuit with empty domain and only bits as codomain. """
        from discopy.quantum.gates import Bits, Ket
        circuit = self
        if circuit.dom:
            init = Id(0).tensor(*(
                Bits(0) if x.name == "bit" else Ket(0) for x in circuit.dom))
            circuit = init >> circuit
        if circuit.cod != bit ** len(circuit.cod):
            discards = Id(0).tensor(*(
                Discard() if x.name == "qubit"
                else Id(bit) for x in circuit.cod))
            circuit = circuit >> discards
        return circuit

    def eval(self, *others, backend=None, mixed=False,
             contractor=None, **params):
        """
        Evaluate a circuit on a backend, or simulate it with numpy.

        Parameters
        ----------
        others : :class:`discopy.quantum.circuit.Circuit`
            Other circuits to process in batch.
        backend : pytket.Backend, optional
            Backend on which to run the circuit, if none then we apply
            :class:`discopy.tensor.Functor` or :class:`CQMapFunctor` instead.
        mixed : bool, optional
            Whether to apply :class:`discopy.tensor.Functor`
            or :class:`CQMapFunctor`.
        contractor : callable, optional
            Use :class:`tensornetwork` contraction
            instead of discopy's basic eval feature.
        params : kwargs, optional
            Get passed to Circuit.get_counts.

        Returns
        -------
        tensor : :class:`discopy.tensor.Tensor`
            If :code:`backend is not None` or :code:`mixed=False`.
        cqmap : :class:`CQMap`
            Otherwise.

        Examples
        --------
        We can evaluate a pure circuit (i.e. with :code:`not circuit.is_mixed`)
        as a unitary :class:`discopy.tensor.Tensor` or as a :class:`CQMap`:

        >>> from discopy.quantum import *

        >>> H.eval().round(2)  # doctest: +ELLIPSIS
        Tensor(dom=Dim(2), cod=Dim(2), array=[0.71+0.j, ..., -0.71+0.j])
        >>> H.eval(mixed=True).round(1)  # doctest: +ELLIPSIS
        CQMap(dom=Q(Dim(2)), cod=Q(Dim(2)), array=[0.5+0.j, ..., 0.5+0.j])

        We can evaluate a mixed circuit as a :class:`CQMap`:

        >>> assert Measure().eval()\\
        ...     == CQMap(dom=Q(Dim(2)), cod=C(Dim(2)),
        ...              array=[1, 0, 0, 0, 0, 0, 0, 1])
        >>> circuit = Bits(1, 0) @ Ket(0) >> Discard(bit ** 2 @ qubit)
        >>> assert circuit.eval() == CQMap(dom=CQ(), cod=CQ(), array=[1])

        We can execute any circuit on a `pytket.Backend`:

        >>> circuit = Ket(0, 0) >> sqrt(2) @ H @ X >> CX >> Measure() @ Bra(0)
        >>> from discopy.quantum.tk import mockBackend
        >>> backend = mockBackend({(0, 1): 512, (1, 0): 512})
        >>> assert circuit.eval(backend, n_shots=2**10).round()\\
        ...     == Tensor(dom=Dim(1), cod=Dim(2), array=[0., 1.])
        """
        from discopy.quantum import cqmap
        if contractor is not None:
            array = contractor(*self.to_tn(mixed=mixed)).tensor
            if self.is_mixed or mixed:
                f = cqmap.Functor()
                return cqmap.CQMap(f(self.dom), f(self.cod), array)
            f = tensor.Functor(lambda x: x[0].dim, {})
            return Tensor(f(self.dom), f(self.cod), array)

        from discopy import cqmap
        from discopy.quantum.gates import Bits, scalar
        if len(others) == 1 and not isinstance(others[0], Circuit):
            # This allows the syntax :code:`circuit.eval(backend)`
            return self.eval(backend=others[0], mixed=mixed, **params)
        if backend is None:
            if others:
                return [circuit.eval(mixed=mixed, **params)
                        for circuit in (self, ) + others]
            functor = cqmap.Functor() if mixed or self.is_mixed\
                else tensor.Functor(lambda x: x[0].dim, lambda f: f.array)
            box = functor(self)
            return type(box)(box.dom, box.cod, box.array + 0j)
        circuits = [circuit.to_tk() for circuit in (self, ) + others]
        results, counts = [], circuits[0].get_counts(
            *circuits[1:], backend=backend, **params)
        for i, circuit in enumerate(circuits):
            n_bits = len(circuit.post_processing.dom)
            result = Tensor.zero(Dim(1), Dim(*(n_bits * (2, ))))
            for bitstring, count in counts[i].items():
                result += (scalar(count) @ Bits(*bitstring)).eval()
            if circuit.post_processing:
                result = result >> circuit.post_processing.eval()
            results.append(result)
        return results if len(results) > 1 else results[0]

    def get_counts(self, *others, backend=None, **params):
        """
        Get counts from a backend, or simulate them with numpy.

        Parameters
        ----------
        others : :class:`discopy.quantum.circuit.Circuit`
            Other circuits to process in batch.
        backend : pytket.Backend, optional
            Backend on which to run the circuit, if none then `numpy`.
        n_shots : int, optional
            Number of shots, default is :code:`2**10`.
        measure_all : bool, optional
            Whether to measure all qubits, default is :code:`False`.
        normalize : bool, optional
            Whether to normalize the counts, default is :code:`True`.
        post_select : bool, optional
            Whether to perform post-selection, default is :code:`True`.
        scale : bool, optional
            Whether to scale the output, default is :code:`True`.
        seed : int, optional
            Seed to feed the backend, default is :code:`None`.
        compilation : callable, optional
            Compilation function to apply before getting counts.

        Returns
        -------
        counts : dict
            From bitstrings to counts.

        Examples
        --------
        >>> from discopy.quantum import *
        >>> circuit = H @ X >> CX >> Measure(2)
        >>> from discopy.quantum.tk import mockBackend
        >>> backend = mockBackend({(0, 1): 512, (1, 0): 512})
        >>> circuit.get_counts(backend, n_shots=2**10)
        {(0, 1): 0.5, (1, 0): 0.5}
        """
        if len(others) == 1 and not isinstance(others[0], Circuit):
            # This allows the syntax :code:`circuit.get_counts(backend)`
            return self.get_counts(backend=others[0], **params)
        if backend is None:
            if others:
                return [circuit.get_counts(**params)
                        for circuit in (self, ) + others]
            utensor, counts = self.init_and_discard().eval(), dict()
            for i in range(2**len(utensor.cod)):
                bits = index2bitstring(i, len(utensor.cod))
                if utensor.array[bits]:
                    counts[bits] = utensor.array[bits].real
            return counts
        counts = self.to_tk().get_counts(
            *(other.to_tk() for other in others), backend=backend, **params)
        return counts if len(counts) > 1 else counts[0]

    def measure(self, mixed=False):
        """
        Measure a circuit on the computational basis using :code:`numpy`.

        Parameters
        ----------
        mixed : bool, optional
            Whether to apply :class:`tensor.Functor` or :class:`cqmap.Functor`.

        Returns
        -------
        array : numpy.ndarray
        """
        from discopy.quantum.gates import Bra, Ket
        if mixed or self.is_mixed:
            return self.init_and_discard().eval(mixed=True).array.real
        state = (Ket(*(len(self.dom) * [0])) >> self).eval()
        effects = [Bra(*index2bitstring(j, len(self.cod))).eval()
                   for j in range(2 ** len(self.cod))]
        array = Tensor.np.zeros(len(self.cod) * (2, )) + 0j
        for effect in effects:
            array +=\
                effect.array * Tensor.np.absolute((state >> effect).array) ** 2
        return array

    def to_tn(self, mixed=False):
        """
        Send a diagram to a mixed :code:`tensornetwork`.

        Parameters
        ----------
        mixed : bool, default: False
            Whether to perform mixed (also known as density matrix) evaluation
            of the circuit.

        Returns
        -------
        nodes : :class:`tensornetwork.Node`
            Nodes of the network.

        output_edge_order : list of :class:`tensornetwork.Edge`
            Output edges of the network.
        """
        if not mixed and not self.is_mixed:
            return super().to_tn()

        import tensornetwork as tn
        from discopy.quantum import (
            qubit, bit, ClassicalGate, Copy, Match, Discard, SWAP)
        for box in self.boxes + [self]:
            if set(box.dom @ box.cod) - set(bit @ qubit):
                raise ValueError(
                    "Only circuits with qubits and bits are supported.")

        # try to decompose some gates
        diag = Id(self.dom)
        last_i = 0
        for i, box in enumerate(self.boxes):
            if hasattr(box, '_decompose'):
                decomp = box._decompose()
                diag >>= self[last_i:i]
                left, _, right = self.layers[i]
                diag >>= Id(left) @ decomp @ Id(right)
                last_i = i + 1
        diag >>= self[last_i:]
        self = diag

        c_nodes = [tn.CopyNode(2, 2, f'c_input_{i}', dtype=complex)
                   for i in range(self.dom.count(bit))]
        q_nodes1 = [tn.CopyNode(2, 2, f'q1_input_{i}', dtype=complex)
                    for i in range(self.dom.count(qubit))]
        q_nodes2 = [tn.CopyNode(2, 2, f'q2_input_{i}', dtype=complex)
                    for i in range(self.dom.count(qubit))]

        inputs = [n[0] for n in c_nodes + q_nodes1 + q_nodes2]
        c_scan = [n[1] for n in c_nodes]
        q_scan1 = [n[1] for n in q_nodes1]
        q_scan2 = [n[1] for n in q_nodes2]
        nodes = c_nodes + q_nodes1 + q_nodes2
        for box, layer, offset in zip(self.boxes, self.layers, self.offsets):
            if box == Circuit.swap(bit, bit):
                left, _, _ = layer
                c_offset = left.count(bit)
                c_scan[c_offset], c_scan[c_offset + 1] =\
                    c_scan[c_offset + 1], c_scan[c_offset]
            elif box.is_mixed or isinstance(box, ClassicalGate):
                c_dom = box.dom.count(bit)
                q_dom = box.dom.count(qubit)
                c_cod = box.cod.count(bit)
                q_cod = box.cod.count(qubit)
                left, _, _ = layer
                c_offset = left.count(bit)
                q_offset = left.count(qubit)
                if isinstance(box, Discard):
                    assert box.n_qubits == 1
                    tn.connect(q_scan1[q_offset], q_scan2[q_offset])
                    del q_scan1[q_offset]
                    del q_scan2[q_offset]
                    continue
                if isinstance(box, (Copy, Match, Measure, Encode)):
                    assert len(box.dom) == 1 or len(box.cod) == 1
                    node = tn.CopyNode(3, 2, 'cq_' + str(box), dtype=complex)
                else:
                    # only unoptimised gate is MixedState()
                    array = box.eval(mixed=True).array
                    node = tn.Node(array + 0j, 'cq_' + str(box))
                for i in range(c_dom):
                    tn.connect(c_scan[c_offset + i], node[i])
                for i in range(q_dom):
                    tn.connect(q_scan1[q_offset + i], node[c_dom + i])
                for i in range(q_dom):
                    tn.connect(q_scan2[q_offset + i], node[c_dom + q_dom + i])
                cq_dom = c_dom + 2 * q_dom
                c_edges = node[cq_dom:cq_dom + c_cod]
                q_edges1 = node[cq_dom + c_cod:cq_dom + c_cod + q_cod]
                q_edges2 = node[cq_dom + c_cod + q_cod:]
                c_scan = (c_scan[:c_offset] + c_edges
                          + c_scan[c_offset + c_dom:])
                q_scan1 = (q_scan1[:q_offset] + q_edges1
                           + q_scan1[q_offset + q_dom:])
                q_scan2 = (q_scan2[:q_offset] + q_edges2
                           + q_scan2[q_offset + q_dom:])
                nodes.append(node)
            else:
                left, _, _ = layer
                q_offset = left[:offset + 1].count(qubit)
                if box == SWAP:
                    q_scan1[q_offset], q_scan1[q_offset + 1] =\
                        q_scan1[q_offset + 1], q_scan1[q_offset]
                    q_scan2[q_offset], q_scan2[q_offset + 1] =\
                        q_scan2[q_offset + 1], q_scan2[q_offset]
                    continue
                utensor = box.array
                node1 = tn.Node(Tensor.np.conj(utensor) + 0j, 'q1_' + str(box))
                node2 = tn.Node(utensor + 0j, 'q2_' + str(box))

                for i in range(len(box.dom)):
                    tn.connect(q_scan1[q_offset + i], node1[i])
                    tn.connect(q_scan2[q_offset + i], node2[i])

                edges1 = node1[len(box.dom):]
                edges2 = node2[len(box.dom):]
                q_scan1 = (q_scan1[:q_offset] + edges1
                           + q_scan1[q_offset + len(box.dom):])
                q_scan2 = (q_scan2[:q_offset] + edges2
                           + q_scan2[q_offset + len(box.dom):])
                nodes.extend([node1, node2])
        outputs = c_scan + q_scan1 + q_scan2
        return nodes, inputs + outputs

    def to_tk(self):
        """
        Export to t|ket>.

        Returns
        -------
        tk_circuit : pytket.Circuit
            A :class:`pytket.Circuit`.

        Note
        ----
        * No measurements are performed.
        * SWAP gates are treated as logical swaps.
        * If the circuit contains scalars or a :class:`Bra`,
          then :code:`tk_circuit` will hold attributes
          :code:`post_selection` and :code:`scalar`.

        Examples
        --------
        >>> from discopy.quantum import *

        >>> bell_test = H @ Id(1) >> CX >> Measure() @ Measure()
        >>> bell_test.to_tk()
        tk.Circuit(2, 2).H(0).CX(0, 1).Measure(0, 0).Measure(1, 1)

        >>> circuit0 = sqrt(2) @ H @ Rx(0.5) >> CX >> Measure() @ Discard()
        >>> circuit0.to_tk()
        tk.Circuit(2, 1).H(0).Rx(1.0, 1).CX(0, 1).Measure(0, 0).scale(2)

        >>> circuit1 = Ket(1, 0) >> CX >> Id(1) @ Ket(0) @ Id(1)
        >>> circuit1.to_tk()
        tk.Circuit(3).X(0).CX(0, 2)

        >>> circuit2 = X @ Id(2) >> Id(1) @ SWAP >> CX @ Id(1) >> Id(1) @ SWAP
        >>> circuit2.to_tk()
        tk.Circuit(3).X(0).CX(0, 2)

        >>> circuit3 = Ket(0, 0)\\
        ...     >> H @ Id(1)\\
        ...     >> Id(1) @ X\\
        ...     >> CX\\
        ...     >> Id(1) @ Bra(0)
        >>> print(repr(circuit3.to_tk()))
        tk.Circuit(2, 1).H(0).X(1).CX(0, 1).Measure(1, 0).post_select({0: 0})
        """
        # pylint: disable=import-outside-toplevel
        from discopy.quantum.tk import to_tk
        return to_tk(self)

    def to_pennylane(self, probabilities=False):
        """
        Export DisCoPy circuit to PennylaneCircuit.

        Parameters
        ----------
        probabilties : bool, default: False
            If True, the PennylaneCircuit will return the normalized
            probabilties of measuring the computational basis states
            when run. If False, it returns the unnormalized quantum
            states in the computational basis.

        Returns
        -------
        :class:`discopy.quantum.pennylane.PennylaneCircuit`
        """

        # pylint: disable=import-outside-toplevel
        from discopy.quantum.pennylane import to_pennylane
        return to_pennylane(self, probabilities=probabilities)

    @staticmethod
    def from_tk(*tk_circuits):
        """
        Translate a :class:`pytket.Circuit` into a :class:`Circuit`, or
        a list of :class:`pytket` circuits into a :class:`Sum`.

        Parameters
        ----------
        tk_circuits : pytket.Circuit
            potentially with :code:`scalar` and
            :code:`post_selection` attributes.

        Returns
        -------
        circuit : :class:`Circuit`
            Such that :code:`Circuit.from_tk(circuit.to_tk()) == circuit`.

        Note
        ----
        * :meth:`Circuit.init_and_discard` is applied beforehand.
        * SWAP gates are introduced when applying gates to non-adjacent qubits.

        Examples
        --------
        >>> from discopy.quantum import *
        >>> import pytket as tk

        >>> c = Rz(0.5) @ Id(1) >> Id(1) @ Rx(0.25) >> CX
        >>> assert Circuit.from_tk(c.to_tk()) == c.init_and_discard()

        >>> tk_GHZ = tk.Circuit(3).H(1).CX(1, 2).CX(1, 0)
        >>> pprint = lambda c: print(str(c).replace(' >>', '\\n  >>'))
        >>> pprint(Circuit.from_tk(tk_GHZ))
        Ket(0)
          >> Id(1) @ Ket(0)
          >> Id(2) @ Ket(0)
          >> Id(1) @ H @ Id(1)
          >> Id(1) @ CX
          >> SWAP @ Id(1)
          >> CX @ Id(1)
          >> SWAP @ Id(1)
          >> Discard(qubit) @ Id(2)
          >> Discard(qubit) @ Id(1)
          >> Discard(qubit)
        >>> circuit = Ket(1, 0) >> CX >> Id(1) @ Ket(0) @ Id(1)
        >>> print(Circuit.from_tk(circuit.to_tk())[3:-3])
        X @ Id(2) >> Id(1) @ SWAP >> CX @ Id(1) >> Id(1) @ SWAP

        >>> bell_state = Circuit.caps(qubit, qubit)
        >>> bell_effect = bell_state[::-1]
        >>> circuit = bell_state @ Id(1) >> Id(1) @ bell_effect >> Bra(0)
        >>> pprint(Circuit.from_tk(circuit.to_tk())[3:])
        H @ Id(2)
          >> CX @ Id(1)
          >> Id(1) @ CX
          >> Id(1) @ H @ Id(1)
          >> Bra(0) @ Id(2)
          >> Bra(0) @ Id(1)
          >> Bra(0)
          >> scalar(4)
        """
        # pylint: disable=import-outside-toplevel
        from discopy.quantum.tk import from_tk
        if not tk_circuits:
            return Sum([], qubit ** 0, qubit ** 0)
        if len(tk_circuits) == 1:
            return from_tk(tk_circuits[0])
        return sum(Circuit.from_tk(c) for c in tk_circuits)

    def grad(self, var, **params):
        """
        Gradient with respect to :code:`var`.

        Parameters
        ----------
        var : sympy.Symbol
            Differentiated variable.

        Returns
        -------
        circuit : `discopy.quantum.circuit.Sum`

        Examples
        --------
        >>> from sympy.abc import phi
        >>> from discopy.quantum import *
        >>> circuit = Rz(phi / 2) @ Rz(phi + 1) >> CX
        >>> assert circuit.grad(phi, mixed=False)\\
        ...     == (Rz(phi / 2) @ scalar(pi) @ Rz(phi + 1.5) >> CX)\\
        ...     + (scalar(pi/2) @ Rz(phi/2 + .5) @ Rz(phi + 1) >> CX)
        """
        return super().grad(var, **params)

    def jacobian(self, variables, **params):
        """
        Jacobian with respect to :code:`variables`.

        Parameters
        ----------
        variables : List[sympy.Symbol]
            Differentiated variables.

        Returns
        -------
        circuit : `discopy.quantum.circuit.Sum`
            with :code:`circuit.dom == self.dom`
            and :code:`circuit.cod == Digit(len(variables)) @ self.cod`.

        Examples
        --------
        >>> from sympy.abc import x, y
        >>> from discopy.quantum.gates import Bits, Ket, Rx, Rz
        >>> circuit = Ket(0) >> Rx(x) >> Rz(y)
        >>> assert circuit.jacobian([x, y])\\
        ...     == (Bits(0) @ circuit.grad(x)) + (Bits(1) @ circuit.grad(y))
        >>> assert not circuit.jacobian([])
        >>> assert circuit.jacobian([x]) == circuit.grad(x)
        """
        if not variables:
            return Sum([], self.dom, self.cod)
        if len(variables) == 1:
            return self.grad(variables[0], **params)
        from discopy.quantum.gates import Digits
        return sum(Digits(i, dim=len(variables)) @ self.grad(x, **params)
                   for i, x in enumerate(variables))

    def draw(self, **params):
        """ We draw the labels of a circuit whenever it's mixed. """
        draw_type_labels = params.get('draw_type_labels') or self.is_mixed
        params = dict({'draw_type_labels': draw_type_labels}, **params)
        return super().draw(**params)

    @staticmethod
    def swap(left, right):
        return monoidal.Diagram.swap(
            left, right, ar_factory=Circuit, swap_factory=Swap)

    @staticmethod
    def permutation(perm, dom=None, inverse=False):
        if dom is None:
            dom = qubit ** len(perm)
        return monoidal.Diagram.permutation(
            perm, dom, ar_factory=Circuit, inverse=inverse)

    @staticmethod
    def cups(left, right):
        from discopy.quantum.gates import CX, H, sqrt, Bra, Match

        def cup_factory(left, right):
            if left == right == qubit:
                return CX >> H @ sqrt(2) @ Id(1) >> Bra(0, 0)
            if left == right == bit:
                return Match() >> Discard(bit)
            raise ValueError
        return rigid.cups(
            left, right, ar_factory=Circuit, cup_factory=cup_factory)

    @staticmethod
    def caps(left, right):
        return Circuit.cups(left, right).dagger()

    @staticmethod
    def spiders(n_legs_in, n_legs_out, dim):
        from discopy.quantum.gates import CX, H, Bra, sqrt
        t = rigid.Ty('PRO')

        if len(dim) == 0:
            return Id()

        def decomp_ar(spider):
            return spider.decompose()

        def spider_ar(spider):
            dom, cod = len(spider.dom), len(spider.cod)
            if dom < cod:
                return spider_ar(spider.dagger()).dagger()
            circ = Id(qubit)
            if dom == 2:
                circ = CX >> Id(qubit) @ Bra(0)
            if cod == 0:
                circ >>= H >> Bra(0) @ sqrt(2)

            return circ

        diag = Diagram.spiders(n_legs_in, n_legs_out, t ** len(dim))
        decomp = monoidal.Functor(ob={t: t}, ar=decomp_ar)
        to_circ = monoidal.Functor(ob={t: qubit}, ar=spider_ar,
                                   ar_factory=Circuit, ob_factory=Ty)
        circ = to_circ(decomp(diag))
        return circ

    def _apply_gate(self, gate, position):
        """ Apply gate at position """
        if position < 0 or position >= len(self.cod):
            raise ValueError(f'Index {position} out of range.')
        left = Id(position)
        right = Id(len(self.cod) - position - len(gate.dom))
        return self >> left @ gate @ right

    def _apply_controlled(self, base_gate, *xs):
        from discopy.quantum import Controlled
        if len(set(xs)) != len(xs):
            raise ValueError(f'Indices {xs} not unique.')
        if min(xs) < 0 or max(xs) >= len(self.cod):
            raise ValueError(f'Indices {xs} out of range.')
        before = sorted(filter(lambda x: x < xs[-1], xs[:-1]))
        after = sorted(filter(lambda x: x > xs[-1], xs[:-1]))
        gate = base_gate
        last_x = xs[-1]
        for x in before[::-1]:
            gate = Controlled(gate, distance=last_x - x)
            last_x = x
        last_x = xs[-1]
        for x in after[::-1]:
            gate = Controlled(gate, distance=last_x - x)
            last_x = x
        return self._apply_gate(gate, min(xs))

    def H(self, x):
        """ Apply Hadamard gate to circuit. """
        from discopy.quantum import H
        return self._apply_gate(H, x)

    def S(self, x):
        """ Apply S gate to circuit. """
        from discopy.quantum import S
        return self._apply_gate(S, x)

    def X(self, x):
        """ Apply Pauli X gate to circuit. """
        from discopy.quantum import X
        return self._apply_gate(X, x)

    def Y(self, x):
        """ Apply Pauli Y gate to circuit. """
        from discopy.quantum import Y
        return self._apply_gate(Y, x)

    def Z(self, x):
        """ Apply Pauli Z gate to circuit. """
        from discopy.quantum import Z
        return self._apply_gate(Z, x)

    def Rx(self, phase, x):
        """ Apply Rx gate to circuit. """
        from discopy.quantum import Rx
        return self._apply_gate(Rx(phase), x)

    def Ry(self, phase, x):
        """ Apply Rx gate to circuit. """
        from discopy.quantum import Ry
        return self._apply_gate(Ry(phase), x)

    def Rz(self, phase, x):
        """ Apply Rz gate to circuit. """
        from discopy.quantum import Rz
        return self._apply_gate(Rz(phase), x)

    def CX(self, x, y):
        """ Apply Controlled X / CNOT gate to circuit. """
        from discopy.quantum import X
        return self._apply_controlled(X, x, y)

    def CY(self, x, y):
        """ Apply Controlled Y gate to circuit. """
        from discopy.quantum import Y
        return self._apply_controlled(Y, x, y)

    def CZ(self, x, y):
        """ Apply Controlled Z gate to circuit. """
        from discopy.quantum import Z
        return self._apply_controlled(Z, x, y)

    def CCX(self, x, y, z):
        """ Apply Controlled CX / Toffoli gate to circuit. """
        from discopy.quantum import X
        return self._apply_controlled(X, x, y, z)

    def CCZ(self, x, y, z):
        """ Apply Controlled CZ gate to circuit. """
        from discopy.quantum import Z
        return self._apply_controlled(Z, x, y, z)

    def CRx(self, phase, x, y):
        """ Apply Controlled Rx gate to circuit. """
        from discopy.quantum import Rx
        return self._apply_controlled(Rx(phase), x, y)

    def CRz(self, phase, x, y):
        """ Apply Controlled Rz gate to circuit. """
        from discopy.quantum import Rz
        return self._apply_controlled(Rz(phase), x, y)

    ty_factory = Ty


class Box(tensor.Box, Circuit):
    """
    Boxes in a circuit diagram.

    Parameters
    ----------
    name : any
    dom : discopy.quantum.circuit.Ty
    cod : discopy.quantum.circuit.Ty
    is_mixed : bool, optional
        Whether the box is mixed, default is :code:`True`.
    _dagger : bool, optional
        If set to :code:`None` then the box is self-adjoint.
    """
    def __init__(self, name, dom, cod,
                 is_mixed=True, data=None, _dagger=False, _conjugate=False):
        if dom and not isinstance(dom, Ty):
            raise TypeError(messages.type_err(Ty, dom))
        if cod and not isinstance(cod, Ty):
            raise TypeError(messages.type_err(Ty, cod))
        z = 1 if _conjugate else 0
        self._conjugate = _conjugate
        rigid.Box.__init__(
            self, name, dom, cod, data=data, _dagger=_dagger, _z=z)
        Circuit.__init__(self, dom, cod, [self], [0])
        if not is_mixed:
            if all(isinstance(x, Digit) for x in dom @ cod):
                self.classical = True
            elif all(isinstance(x, Qudit) for x in dom @ cod):
                self.classical = False
            else:
                raise ValueError(
                    "dom and cod should be Digits only or Qudits only.")
        self._mixed = is_mixed

    def grad(self, var, **params):
        if var not in self.free_symbols:
            return Sum([], self.dom, self.cod)
        raise NotImplementedError

    @property
    def is_mixed(self):
        return self._mixed


class Sum(tensor.Sum, Box):
    """ Sums of circuits. """
    @staticmethod
    def upgrade(old):
        return Sum(old.terms, old.dom, old.cod)

    @property
    def is_mixed(self):
        return any(circuit.is_mixed for circuit in self.terms)

    def get_counts(self, backend=None, **params):
        if not self.terms:
            return {}
        if len(self.terms) == 1:
            return self.terms[0].get_counts(backend=backend, **params)
        counts = Circuit.get_counts(*self.terms, backend=backend, **params)
        result = {}
        for circuit_counts in counts:
            for bitstring, count in circuit_counts.items():
                result[bitstring] = result.get(bitstring, 0) + count
        return result

    def eval(self, backend=None, mixed=False, **params):
        mixed = mixed or any(t.is_mixed for t in self.terms)
        if not self.terms:
            return 0
        if len(self.terms) == 1:
            return self.terms[0].eval(backend=backend, mixed=mixed, **params)
        return sum(
            Circuit.eval(*self.terms, backend=backend, mixed=mixed, **params))

    def grad(self, var, **params):
        return sum(circuit.grad(var, **params) for circuit in self.terms)

    def to_tk(self):
        return [circuit.to_tk() for circuit in self.terms]


class Swap(tensor.Swap, Box):
    """ Implements swaps of circuit wires. """
    @property
    def is_mixed(self):
        return self.left != self.right

    def dagger(self):
        return Swap(self.right, self.left)

    def conjugate(self):
        return Swap(self.right, self.left)

    l = r = property(conjugate)

    def __str__(self):
        return "SWAP" if self.dom == qubit ** 2 else super().__str__()


class Functor(frobenius.Functor):
    """ Functors into :class:`Circuit`. """
    cod = Category(Ty, Circuit)

    def __init__(self, ob, ar):
        if isinstance(ob, Mapping):
            ob = {x: qubit ** y if isinstance(y, int) else y
                  for x, y in ob.items()}
        super().__init__(ob, ar)



def index2bitstring(i, length):
    """ Turns an index into a bitstring of a given length. """
    if i >= 2 ** length:
        raise ValueError("Index should be less than 2 ** length.")
    if not i and not length:
        return ()
    return tuple(map(int, '{{:0{}b}}'.format(length).format(i)))


def bitstring2index(bitstring):
    """ Turns a bitstring into an index. """
    return sum(value * 2 ** i for i, value in enumerate(bitstring[::-1]))


Circuit.braid_factory, Circuit.sum_factory = Swap, Sum
bit, qubit = Ty(Digit(2)), Ty(Qudit(2))
Id = Circuit.id
