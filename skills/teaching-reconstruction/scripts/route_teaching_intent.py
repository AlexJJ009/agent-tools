#!/usr/bin/env python3
"""Compatibility entry: keyword-only semantic routing has been retired.

Existing callers remain usable, but must supply an Agent-authored decision to
select a capability. A prompt alone returns a handoff, never starts teaching.
"""
from __future__ import annotations
from typing import Any


def route_request(prompt: str, decision: dict[str, Any] | None = None) -> dict[str, Any]:
    if decision is None:
        return {'owner':'none','mode':'semantic-decision-required',
                'reason':'Main Agent must classify the request and active context; keywords are not authority.'}
    activity=decision.get('activity')
    mode=decision.get('interaction_mode')
    if activity not in {'delivery','learning','writing','curation','answer'} or mode not in {'direct','guided','practice','review'}:
        raise ValueError('invalid Agent decision')
    selected=decision.get('selected_skills',[])
    if not isinstance(selected,list) or not all(isinstance(x,str) for x in selected):
        raise ValueError('selected_skills must be a string list')
    owner=next((s for s in selected if s in {'teaching-reconstruction','academic-writing','learning-artifact-compiler'}),'none')
    return {'owner':owner,'mode':mode,'activity':activity,'delegates':tuple(s for s in selected if s!=owner)}


if __name__=='__main__':
    import argparse
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prompt',nargs='*')
    parser.add_argument('--decision',type=Path,help='JSON Main Agent decision, never a keyword list')
    args=parser.parse_args()
    print(json.dumps(route_request(' '.join(args.prompt),json.loads(args.decision.read_text()) if args.decision else None),ensure_ascii=False))
