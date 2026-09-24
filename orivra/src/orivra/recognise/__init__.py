"""Recognisers: the checks that decide whether something may be asserted.

A recogniser answers a question the contract layer can only refuse to have answered badly.
`contracts/edges.py` refuses a source-stated edge whose evidence contradicts itself; this
package is where the evidence is computed from the message text, so a builder cannot supply
four booleans and call the gates passed.
"""

from __future__ import annotations
