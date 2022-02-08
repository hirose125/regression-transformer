"""
This is the selfies decoder as implemented in v1.0.4.
Taken from: https://github.com/aspuru-guzik-group/selfies
"""

from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Tuple, Union

from itertools import product
from typing import Dict, List, Optional, Set, Tuple

default_bond_constraints = {
    'H': 1,
    'F': 1,
    'Cl': 1,
    'Br': 1,
    'I': 1,
    'O': 2,
    'O+1': 3,
    'O-1': 1,
    'N': 3,
    'N+1': 4,
    'N-1': 2,
    'C': 4,
    'C+1': 5,
    'C-1': 3,
    'P': 5,
    'P+1': 6,
    'P-1': 4,
    'S': 6,
    'S+1': 7,
    'S-1': 5,
    '?': 8,
}

octet_rule_bond_constraints = dict(default_bond_constraints)
octet_rule_bond_constraints.update(
    {'S': 2, 'S+1': 3, 'S-1': 1, 'P': 3, 'P+1': 4, 'P-1': 2}
)

hypervalent_bond_constraints = dict(default_bond_constraints)
hypervalent_bond_constraints.update({'Cl': 7, 'Br': 7, 'I': 7, 'N': 5})

_bond_constraints = default_bond_constraints


def get_semantic_robust_alphabet() -> Set[str]:
    """Returns a subset of all symbols that are semantically constrained
    by :mod:`selfies`.
    These semantic constraints can be configured with
    :func:`selfies.set_semantic_constraints`.
    :return: a subset of all symbols that are semantically constrained.
    """

    alphabet_subset = set()

    organic_subset = {'B', 'C', 'N', 'O', 'S', 'P', 'F', 'Cl', 'Br', 'I'}
    bonds = {'': 1, '=': 2, '#': 3}

    # add atomic symbols
    for (a, c), (b, m) in product(_bond_constraints.items(), bonds.items()):

        if (m > c) or (a == '?'):
            continue

        if a in organic_subset:
            symbol = "[{}{}]".format(b, a)
        else:
            symbol = "[{}{}expl]".format(b, a)

        alphabet_subset.add(symbol)

    # add branch and ring symbols
    for i in range(1, 4):
        alphabet_subset.add("[Ring{}]".format(i))
        alphabet_subset.add("[Expl=Ring{}]".format(i))

        for j in range(1, 4):
            alphabet_subset.add("[Branch{}_{}]".format(i, j))

    return alphabet_subset


def get_default_constraints() -> Dict[str, int]:
    """Returns the preset "default" bond constraint settings.
    :return: the default constraint settings.
    """

    global default_bond_constraints
    return dict(default_bond_constraints)


def get_octet_rule_constraints() -> Dict[str, int]:
    """Returns the preset "octet rule" bond constraint settings. These
    constraints are a harsher version of the default constraints, so that
    the `octet rule <https://en.wikipedia.org/wiki/Octet_rule>`_
    is obeyed. In particular, ``S`` and ``P`` are
    restricted to a 2 and 3 bond capacity, respectively (and similarly with
    ``S+``, ``S-``, ``P+``, ``P-``).
    :return: the octet rule constraint settings.
    """

    global octet_rule_bond_constraints
    return dict(octet_rule_bond_constraints)


def get_hypervalent_constraints() -> Dict[str, int]:
    """Returns the preset "hypervalent" bond constraint settings. These
    constraints are a relaxed version of the default constraints, to allow
    for `hypervalent molecules
    <https://en.wikipedia.org/wiki/Hypervalent_molecule>`_.
    In particular, ``Cl``, ``Br``, and ``I``
    are relaxed to a 7 bond capacity, and ``N`` is relaxed to a 5 bond
    capacity.
    :return: the hypervalent constraint settings.
    """

    global hypervalent_bond_constraints
    return dict(hypervalent_bond_constraints)


def get_semantic_constraints() -> Dict[str, int]:
    """Returns the semantic bond constraints that :mod:`selfies` is currently
    operating on.
    Returned is the argument of the most recent call of
    :func:`selfies.set_semantic_constraints`, or the default bond constraints
    if the function has not been called yet. Once retrieved, it is copied and
    then returned. See :func:`selfies.set_semantic_constraints` for further
    explanation.
    :return: the bond constraints :mod:`selfies` is currently operating on.
    """

    global _bond_constraints
    return dict(_bond_constraints)


def set_semantic_constraints(bond_constraints: Optional[Dict[str, int]] = None) -> None:
    """Configures the semantic constraints of :mod:`selfies`.
    The SELFIES grammar is enforced dynamically from a dictionary
    ``bond_constraints``. The keys of the dictionary are atoms and/or ions
    (e.g. ``I``, ``Fe+2``). To denote an ion, use the format ``E+C``
    or ``E-C``, where ``E`` is an element and ``C`` is a positive integer.
    The corresponding value is the maximum number of bonds that atom or
    ion can make, between 1 and 8 inclusive. For example, one may have:
        * ``bond_constraints['I'] = 1``
        * ``bond_constraints['C'] = 4``
    :func:`selfies.decoder` will only generate SMILES that respect the bond
    constraints specified by the dictionary. In the example above, both
    ``'[C][=I]'`` and ``'[I][=C]'`` will be translated to ``'CI'`` and
    ``'IC'`` respectively, because ``I`` has been configured to make one bond
    maximally.
    If an atom or ion is not specified in ``bond_constraints``, it will
    by default be constrained to 8 bonds. To change the default setting
    for unrecognized atoms or ions, set ``bond_constraints['?']`` to the
    desired integer (between 1 and 8 inclusive).
    :param bond_constraints: a dictionary representing the semantic
        constraints the updated SELFIES will operate upon. Defaults to
        ``None``; in this case, a default dictionary will be used.
    :return: ``None``.
    """

    global _bond_constraints

    if bond_constraints is None:
        _bond_constraints = default_bond_constraints

    else:

        # error checking
        if '?' not in bond_constraints:
            raise ValueError("bond_constraints missing '?' as a key.")

        for key, value in bond_constraints.items():
            if not (1 <= value <= 8):
                raise ValueError(
                    "bond_constraints['{}'] not between "
                    "1 and 8 inclusive.".format(key)
                )

        _bond_constraints = dict(bond_constraints)


# Symbol State Dict Functions ==============================================


def get_next_state(symbol: str, state: int) -> Tuple[str, int]:
    """Enforces the grammar rules for standard SELFIES symbols.
    Given the current non-branch, non-ring symbol and current derivation
    state, retrieves the derived SMILES symbol and the next derivation
    state.
    :param symbol: a SELFIES symbol that is not a Ring or Branch.
    :param state: the current derivation state.
    :return: a tuple of (1) the derived symbol, and
        (2) the next derivation state.
    """

    if symbol == '[epsilon]':
        return ('', 0) if state == 0 else ('', -1)

    # convert to smiles symbol
    bond = ''
    if symbol[1] in {'/', '\\', '=', '#'}:
        bond = symbol[1]
    bond_num = get_num_from_bond(bond)

    if symbol[-5:] == 'expl]':  # e.g. [C@@Hexpl]
        smiles_symbol = "[{}]".format(symbol[1 + len(bond) : -5])
    else:
        smiles_symbol = symbol[1 + len(bond) : -1]

    # get bond capacity
    element, h_count, charge = parse_atom_symbol(smiles_symbol)

    if charge == 0:
        atom_or_ion = element
    else:
        atom_or_ion = "{}{:+}".format(element, charge)

    max_bonds = _bond_constraints.get(atom_or_ion, _bond_constraints['?'])

    if (h_count > max_bonds) or (h_count == max_bonds and state > 0):
        raise ValueError(
            "too many Hs in symbol '{}'; consider "
            "adjusting bond constraints".format(symbol)
        )
    max_bonds -= h_count  # hydrogens consume 1 bond

    # calculate next state
    if state == 0:
        bond = ''
        next_state = max_bonds
    else:
        if bond_num > min(state, max_bonds):
            bond_num = min(state, max_bonds)
            bond = get_bond_from_num(bond_num)

        next_state = max_bonds - bond_num
        if next_state == 0:
            next_state = -1

    return (bond + smiles_symbol), next_state


# Branch State Dict Functions =================================================


def get_next_branch_state(branch_symbol: str, state: int) -> Tuple[int, int]:
    """Enforces the grammar rules for SELFIES Branch symbols.
    Given the branch symbol and current derivation state, retrieves
    the initial branch derivation state (i.e. the derivation state that the
    new branch begins on), and the next derivation state (i.e. the derivation
    state after the branch is created).
    :param branch_symbol: the branch symbol (e.g. [Branch1_2], [Branch3_1])
    :param state: the current derivation state.
    :return: a tuple of (1) the initial branch state, and
        (2) the next derivation state.
    """

    branch_type = int(branch_symbol[-2])  # branches of the form [BranchL_X]

    if not (1 <= branch_type <= 3):
        raise ValueError("unknown branch symbol '{}'".format(branch_symbol))

    if 2 <= state <= 8:
        branch_init_state = min(state - 1, branch_type)
        next_state = state - branch_init_state
        return branch_init_state, next_state
    else:
        return -1, state


# SELFIES Symbol to N Functions ============================================

_index_alphabet = [
    '[C]',
    '[Ring1]',
    '[Ring2]',
    '[Branch1_1]',
    '[Branch1_2]',
    '[Branch1_3]',
    '[Branch2_1]',
    '[Branch2_2]',
    '[Branch2_3]',
    '[O]',
    '[N]',
    '[=N]',
    '[=C]',
    '[#C]',
    '[S]',
    '[P]',
]

# _alphabet_code takes as a key a SELFIES symbol, and its corresponding value
# is the index of the key.

_alphabet_code = {c: i for i, c in enumerate(_index_alphabet)}


def get_n_from_symbols(*symbols: List[str]) -> int:
    """Computes N from a list of SELFIES symbols.
    Converts a list of SELFIES symbols [c_1, ..., c_n] into a number N.
    This is done by converting each symbol c_n to an integer idx(c_n) via
    ``_alphabet_code``, and then treating the list as a number in base
    len(_alphabet_code). If a symbol is unrecognized, it is given value 0 by
    default.
    :param symbols: a list of SELFIES symbols.
    :return: the corresponding N for ``symbols``.
    """

    N = 0
    for i, c in enumerate(reversed(symbols)):
        N_i = _alphabet_code.get(c, 0) * (len(_alphabet_code) ** i)
        N += N_i
    return N


def get_symbols_from_n(n: int) -> List[str]:
    """Converts an integer n into a list of SELFIES symbols that, if
    passed into ``get_n_from_symbols`` in that order, would have produced n.
    :param n: an integer from 0 to 4095 inclusive.
    :return: a list of SELFIES symbols representing n in base
        ``len(_alphabet_code)``.
    """

    if n == 0:
        return [_index_alphabet[0]]

    symbols = []
    base = len(_index_alphabet)
    while n:
        symbols.append(_index_alphabet[n % base])
        n //= base
    return symbols[::-1]


# Helper Functions ============================================================


def get_num_from_bond(bond_symbol: str) -> int:
    """Retrieves the bond multiplicity from a SMILES symbol representing
    a bond. If ``bond_symbol`` is not known, 1 is returned by default.
    :param bond_symbol: a SMILES symbol representing a bond.
    :return: the bond multiplicity of ``bond_symbol``, or 1 if
        ``bond_symbol`` is not recognized.
    """

    if bond_symbol == "=":
        return 2
    elif bond_symbol == "#":
        return 3
    else:
        return 1


def get_bond_from_num(n: int) -> str:
    """Returns the SMILES symbol representing a bond with multiplicity
    ``n``. More specifically, ``'' = 1`` and ``'=' = 2`` and ``'#' = 3``.
    :param n: either 1, 2, 3.
    :return: the SMILES symbol representing a bond with multiplicity ``n``.
    """

    return ('', '=', '#')[n - 1]


def find_element(atom_symbol: str) -> Tuple[int, int]:
    """Returns the indices of the element component of a SMILES atom symbol.
    That is, if atom_symbol[i:j] is the element substring of the SMILES atom,
    then (i, j) is returned. For example:
        *   _find_element('b') = (0, 1).
        *   _find_element('B') = (0, 1).
        *   _find_element('[13C]') = (3, 4).
        *   _find_element('[nH+]') = (1, 2).
    :param atom_symbol: a SMILES atom.
    :return: a tuple of the indices of the element substring of
        ``atom_symbol``.
    """

    if atom_symbol[0] != '[':
        return 0, len(atom_symbol)

    i = 1
    while atom_symbol[i].isdigit():  # skip isotope number
        i += 1

    if atom_symbol[i + 1].isalpha() and atom_symbol[i + 1] != 'H':
        return i, i + 2
    else:
        return i, i + 1


def parse_atom_symbol(atom_symbol: str) -> Tuple[str, int, int]:
    """Parses a SMILES atom symbol and returns its element component,
    number of associated hydrogens, and charge.
    See http://opensmiles.org/opensmiles.html for the formal grammar
    of SMILES atom symbols. Note that only @ and @@ are currently supported
    as chiral specifications.
    :param atom_symbol: a SMILES atom symbol.
    :return: a tuple of (1) the element of ``atom_symbol``, (2) the hydrogen
        count, and (3) the charge.
    """

    if atom_symbol[0] != '[':
        return atom_symbol, 0, 0

    atom_start, atom_end = find_element(atom_symbol)
    i = atom_end

    # skip chirality
    if atom_symbol[i] == '@':  # e.g. @
        i += 1
    if atom_symbol[i] == '@':  # e.g. @@
        i += 1

    h_count = 0  # hydrogen count
    if atom_symbol[i] == 'H':
        h_count = 1

        i += 1
        if atom_symbol[i].isdigit():  # e.g. [CH2]
            h_count = int(atom_symbol[i])
            i += 1

    charge = 0  # charge count
    if atom_symbol[i] in ('+', '-'):
        charge = 1 if atom_symbol[i] == '+' else -1

        i += 1
        if atom_symbol[i] in ('+', '-'):  # e.g. [Cu++]
            while atom_symbol[i] in ('+', '-'):
                charge += 1 if atom_symbol[i] == '+' else -1
                i += 1

        elif atom_symbol[i].isdigit():  # e.g. [Cu+2]
            s = i
            while atom_symbol[i].isdigit():
                i += 1
            charge *= int(atom_symbol[s:i])

    return atom_symbol[atom_start:atom_end], h_count, charge


def decoder(
    selfies: str, print_error: bool = False, constraints: Optional[str] = None
) -> Optional[str]:
    """Translates a SELFIES into a SMILES.
    The SELFIES to SMILES translation operates based on the :mod:`selfies`
    grammar rules, which can be configured using
    :func:`selfies.set_semantic_constraints`. Given the appropriate settings,
    the decoded SMILES will always be syntactically and semantically correct.
    That is, the output SMILES will satisfy the specified bond constraints.
    Additionally, :func:`selfies.decoder` will attempt to preserve the
    atom and branch order of the input SELFIES.
    :param selfies: the SELFIES to be translated.
    :param print_error: if True, error messages will be printed to console.
        Defaults to False.
    :param constraints: if ``'octet_rule'`` or ``'hypervalent'``,
        the corresponding preset bond constraints will be used instead.
        If ``None``, :func:`selfies.decoder` will use the
        currently configured bond constraints. Defaults to ``None``.
    :return: the SMILES translation of ``selfies``. If an error occurs,
        and ``selfies`` cannot be translated, ``None`` is returned instead.
    :Example:
    >>> import selfies
    >>> selfies.decoder('[C][=C][F]')
    'C=CF'
    .. seealso:: The
        `"octet_rule" <https://en.wikipedia.org/wiki/Octet_rule>`_
        and
        `"hypervalent" <https://en.wikipedia.org/wiki/Hypervalent_molecule>`_
        preset bond constraints
        can be viewed with :func:`selfies.get_octet_rule_constraints` and
        :func:`selfies.get_hypervalent_constraints`, respectively. These
        presets are variants of the "default" bond constraints, which can
        be viewed with :func:`selfies.get_default_constraints`. Their
        differences can be summarized as follows:
            * def. : ``Cl``, ``Br``, ``I``: 1, ``N``: 3, ``P``: 5, ``P+1``: 6, ``P-1``: 4, ``S``: 6, ``S+1``: 7, ``S-1``: 5
            * oct. : ``Cl``, ``Br``, ``I``: 1, ``N``: 3, ``P``: 3, ``P+1``: 4, ``P-1``: 2, ``S``: 2, ``S+1``: 3, ``S-1``: 1
            * hyp. : ``Cl``, ``Br``, ``I``: 7, ``N``: 5, ``P``: 5, ``P+1``: 6, ``P-1``: 4, ``S``: 6, ``S+1``: 7, ``S-1``: 5
    """

    old_constraints = get_semantic_constraints()
    if constraints is None:
        pass
    elif constraints == 'octet_rule':
        set_semantic_constraints(get_octet_rule_constraints())
    elif constraints == 'hypervalent':
        set_semantic_constraints(get_hypervalent_constraints())
    else:
        raise ValueError("unrecognized constraint type")

    try:
        all_smiles = []  # process dot-separated fragments separately

        for s in selfies.split("."):
            smiles = _translate_selfies(s)

            if smiles != "":  # prevent malformed dots (e.g. [C]..[C], .[C][C])
                all_smiles.append(smiles)

        if constraints is not None:  # restore old constraints
            set_semantic_constraints(old_constraints)

        return '.'.join(all_smiles)

    except ValueError as err:
        if constraints is not None:  # restore old constraints
            set_semantic_constraints(old_constraints)

        if print_error:
            print("Decoding error '{}': {}.".format(selfies, err))
        return None


def _parse_selfies(selfies: str) -> Iterable[str]:
    """Parses a SELFIES into its symbols.
    A generator, which parses a SELFIES and yields its symbols
    one-by-one. When no symbols are left in the SELFIES, the empty
    string is infinitely yielded. As a precondition, the input SELFIES contains
    no dots, so all symbols are enclosed by square brackets, e.g. [X].
    :param selfies: the SElFIES string to be parsed.
    :return: an iterable of the symbols of the SELFIES.
    """

    left_idx = selfies.find('[')

    while 0 <= left_idx < len(selfies):
        right_idx = selfies.find(']', left_idx + 1)

        if (selfies[left_idx] != '[') or (right_idx == -1):
            raise ValueError("malformed SELIFES, " "misplaced or missing brackets")

        next_symbol = selfies[left_idx : right_idx + 1]
        left_idx = right_idx + 1

        if next_symbol != '[nop]':  # skip [nop]
            yield next_symbol

    while True:  # no more symbols left
        yield ''


def _parse_selfies_symbols(selfies_symbols: List[str]) -> Iterable[str]:
    """Equivalent to ``_parse_selfies``, except the input SELFIES is presented
    as a list of SELFIES symbols, as opposed to a string.
    :param selfies_symbols: a SELFIES represented as a list of SELFIES symbols.
    :return: an iterable of the symbols of the SELFIES.
    """
    for symbol in selfies_symbols:

        if symbol != '[nop]':
            yield symbol

    while True:
        yield ''


def _translate_selfies(selfies: str) -> str:
    """A helper for ``selfies.decoder``, which translates a SELFIES into a
    SMILES (assuming the input SELFIES contains no dots).
    :param selfies: the SELFIES to be translated.
    :return: the SMILES translation of the SELFIES.
    """

    selfies_gen = _parse_selfies(selfies)

    # derived[i] is a list with three elements:
    #  (1) a string representing the i-th derived atom, and its connecting
    #      bond (e.g. =C, #N, N, C are all possible)
    #  (2) the number of available bonds the i-th atom has to make
    #  (3) the index of the previously derived atom that the i-th derived
    #      atom is bonded to
    # Example: if the 6-th derived atom was 'C', had 2 available bonds,
    # and was connected to the 5-th derived atom by a double bond, then
    # derived[6] = ['=C', 2, 5]
    derived = []

    # each item of <branches> is a key-value pair of indices that represents
    # the branches to be made. If a branch starts at the i-th derived atom
    # and ends at the j-th derived atom, then branches[i] = j. No two
    # branches should start at the same atom, e.g. C((C)Cl)C
    branches = {}

    # each element of <rings> is a tuple of size three that represents the
    # rings to be made, in the same order they appear in the SELFIES (left
    # to right). If the i-th ring is between the j-th and k-th derived atoms
    # (j <= k) and has bond symbol s ('=', '#', '\', etc.), then
    # rings[i] = (j, k, s).
    rings = []

    _translate_selfies_derive(selfies_gen, 0, derived, -1, branches, rings)
    _form_rings_bilocally(derived, rings)

    # create branches
    for lb, rb in branches.items():
        derived[lb][0] = '(' + derived[lb][0]
        derived[rb][0] += ')'

    smiles = ""
    for s, _, _ in derived:  # construct SMILES from <derived>
        smiles += s
    return smiles


# flake8: noqa: C901
# noinspection PyTypeChecker
def _translate_selfies_derive(
    selfies_gen: Iterable[str],
    init_state: int,
    derived: List[List[Union[str, int]]],
    prev_idx: int,
    branches: Dict[int, int],
    rings: List[Tuple[int, int, str]],
) -> None:
    """Recursive helper for _translate_selfies.
    Derives the SMILES symbols one-by-one from a SELFIES, and
    populates derived, branches, and rings. The main chain and side branches
    of the SELFIES are translated recursively. Rings are not actually
    translated, but saved to the rings list to be added later.
    :param selfies_gen: an iterable of the symbols of the SELFIES to be
        translated, created by ``_parse_selfies``.
    :param init_state: the initial derivation state.
    :param derived: see ``derived`` in ``_translate_selfies``.
    :param prev_idx: the index of the previously derived atom, or -1,
        if no atoms have been derived yet.
    :param branches: see ``branches`` in ``_translate_selfies``.
    :param rings: see ``rings`` in ``_translate_selfies``.
    :return: ``None``.
    """

    curr_symbol = next(selfies_gen)
    state = init_state

    while curr_symbol != '' and state >= 0:

        # Case 1: Branch symbol (e.g. [Branch1_2])
        if 'Branch' in curr_symbol:

            branch_init_state, new_state = get_next_branch_state(curr_symbol, state)

            if state <= 1:  # state = 0, 1
                pass  # ignore no symbols

            else:
                L = int(curr_symbol[-4])  # corresponds to [BranchL_X]
                L_symbols = []
                for _ in range(L):
                    L_symbols.append(next(selfies_gen))

                N = get_n_from_symbols(*L_symbols)

                branch_symbols = []
                for _ in range(N + 1):
                    branch_symbols.append(next(selfies_gen))
                branch_gen = _parse_selfies_symbols(branch_symbols)

                branch_start = len(derived)
                _translate_selfies_derive(
                    branch_gen, branch_init_state, derived, prev_idx, branches, rings
                )
                branch_end = len(derived) - 1

                # resolve C((C)Cl)C --> C(C)(Cl)C
                while branch_start in branches:
                    branch_start = branches[branch_start] + 1

                # finally, register the branch in branches
                if branch_start <= branch_end:
                    branches[branch_start] = branch_end

        # Case 2: Ring symbol (e.g. [Ring2])
        elif 'Ring' in curr_symbol:

            new_state = state

            if state == 0:
                pass  # ignore no symbols

            else:
                L = int(curr_symbol[-2])  # corresponds to [RingL]
                L_symbols = []
                for _ in range(L):
                    L_symbols.append(next(selfies_gen))

                N = get_n_from_symbols(*L_symbols)

                left_idx = max(0, prev_idx - (N + 1))
                right_idx = prev_idx

                bond_symbol = ''
                if curr_symbol[1:5] == 'Expl':
                    bond_symbol = curr_symbol[5]

                rings.append((left_idx, right_idx, bond_symbol))

        # Case 3: regular symbol (e.g. [N], [=C], [F])
        else:
            new_symbol, new_state = get_next_state(curr_symbol, state)

            if new_symbol != '':  # in case of [epsilon]
                derived.append([new_symbol, new_state, prev_idx])

                if prev_idx >= 0:
                    bond_num = get_num_from_bond(new_symbol[0])
                    derived[prev_idx][1] -= bond_num

                prev_idx = len(derived) - 1

        curr_symbol = next(selfies_gen)  # update symbol and state
        state = new_state


def _form_rings_bilocally(
    derived: List[List[Union[str, int]]], rings: List[Tuple[int, int, str]]
) -> None:
    """Forms all the rings specified by the rings list, in first-to-last order,
    by updating derived.
    :param derived: see ``derived`` in ``_translate_selfies``.
    :param rings: see ``rings`` in ``_translate_selfies``.
    :return: ``None``.
    """

    # due to the behaviour of allowing multiple rings between the same atom
    # pair, or rings between already bonded atoms, we first resolve all rings
    # so that only valid rings are left and placed into <ring_locs>.
    ring_locs = OrderedDict()

    for left_idx, right_idx, bond_symbol in rings:

        if left_idx == right_idx:  # ring to the same atom forbidden
            continue

        left_end = derived[left_idx]
        right_end = derived[right_idx]
        bond_num = get_num_from_bond(bond_symbol)

        if left_end[1] <= 0 or right_end[1] <= 0:
            continue  # no room for bond

        if bond_num > min(left_end[1], right_end[1]):
            bond_num = min(left_end[1], right_end[1])
            bond_symbol = get_bond_from_num(bond_num)

        # ring is formed between two atoms that are already bonded
        # e.g. CC1C1C --> CC=CC
        if left_idx == right_end[2]:

            right_symbol = right_end[0]

            if right_symbol[0] in {'-', '/', '\\', '=', '#'}:
                old_bond = right_symbol[0]
            else:
                old_bond = ''

            # update bond multiplicity and symbol
            new_bond_num = min(bond_num + get_num_from_bond(old_bond), 3)
            new_bond_symbol = get_bond_from_num(new_bond_num)

            right_end[0] = new_bond_symbol + right_end[0][len(old_bond) :]

        # ring is formed between two atoms that are not bonded, e.g. C1CC1C
        else:
            loc = (left_idx, right_idx)

            if loc in ring_locs:
                # a ring is formed between two atoms that are have previously
                # been bonded by a ring, so ring bond multiplicity is updated

                new_bond_num = min(bond_num + get_num_from_bond(ring_locs[loc]), 3)
                new_bond_symbol = get_bond_from_num(new_bond_num)
                ring_locs[loc] = new_bond_symbol

            else:
                ring_locs[loc] = bond_symbol

        left_end[1] -= bond_num
        right_end[1] -= bond_num

    # finally, use <ring_locs> to add all the rings into <derived>

    ring_counter = 1
    for (left_idx, right_idx), bond_symbol in ring_locs.items():

        ring_id = str(ring_counter)
        if len(ring_id) == 2:
            ring_id = "%" + ring_id
        ring_counter += 1  # increment

        derived[left_idx][0] += bond_symbol + ring_id
        derived[right_idx][0] += bond_symbol + ring_id