"""Bound the repair path after Eastern's failed broad archive search.

The normal strict gate still judges every new illustration. Verified portraits
and primary document excerpts retain their source-specific replacement path.
"""
import copy,json

def saved_plan(folder,user,model,max_tokens,effort):
    """Reuse a complete paid plan with the identical request and model settings."""
    prefix=f'# {model} effort={effort} max_tokens={max_tokens} finish=stop '
    for path in sorted(folder.glob('*reconceive*.md'),reverse=True):
        raw=path.read_text(encoding='utf-8')
        if not raw.startswith(prefix):continue
        try:
            prompt,answer=raw.split('## prompt\n\n',1)[1].split('\n\n## answer\n\n',1)
            if prompt!=user:continue
            result=json.loads(answer)
            if isinstance(result,dict) and isinstance(result.get('shots'),list):return result
        except (ValueError,IndexError):continue
    return None

def install():
    from orchestrator.stages import preflight,story_assets,story
    from orchestrator import llm,config
    original=preflight._replace
    original_planner=preflight._reconceive
    original_json=llm.ask_json
    def cached_json(user,**kw):
        if str(kw.get('tag','')).startswith('reconceive'):
            model=kw.get('model') or config.LLM_MODEL_HEAVY
            cached=saved_plan(config.DATA/'llm_log',user,model,kw.get('max_tokens',8000),kw.get('effort','medium'))
            if cached is not None:
                print('[repair-plan-cache] identical completed plan reused; strict validation follows',flush=True)
                return copy.deepcopy(cached)
        return original_json(user,**kw)
    llm.ask_json=cached_json
    def plan(bad,script,vid,p,neighbours=None):
        planned=[]
        for scene,slot,why in bad:
            candidate=copy.deepcopy(slot)
            if candidate.get('kind')=='archive' and candidate.get('role')!='portrait' and not str(candidate.get('image') or '').startswith('primary_sources/'):
                candidate['no_people']=True
                why+='; replacement will be a clearly labelled objects-only illustration, no recreated historical people or event'
            planned.append((scene,candidate,why))
        return original_planner(planned,script,vid,p,neighbours)
    preflight._reconceive=plan
    def replace(slot,d,model,cost,prompt,attempt,ctx='',vid=''):
        if slot.get('kind')!='archive' or slot.get('role')=='portrait' or str(slot.get('image') or '').startswith('primary_sources/'):
            return original(slot,d,model,cost,prompt,attempt,ctx,vid)
        old=copy.deepcopy(slot);candidate=copy.deepcopy(slot)
        for key in ('archive','credit','year','src_px','portrait_ok','focus_xy','kind','aspect'):candidate.pop(key,None)
        candidate.update(source='image',src=None,image=None,clip_seconds=None,caption='Illustration',no_people=True)
        safe=prompt.rstrip(' ,.')+story_assets.NO_PEOPLE+story.NO_FIGURE+', objects and equipment only, no historical event or person recreated'
        original(candidate,d,model,cost,safe,attempt,ctx,vid)
        path=candidate.get('image')
        if candidate.get('kind')!='image' or not path or not (d/path).is_file():
            slot.clear();slot.update(old)
            print('[repair] '+slot.get('id','?')+': original retained; new illustration unavailable',flush=True)
            return
        preflight._record_reconceived_intent(candidate,ctx)
        slot.clear();slot.update(candidate)
        print('[repair] '+slot.get('id','?')+': labelled illustration purchased; strict recheck pending',flush=True)
    preflight._replace=replace
