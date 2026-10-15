def test_positive_average_contract():
    import ast,importlib.util,json,math
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    p=root/'Intelligent-Audio-TEST/backend/utils/report/aggregation_strategies.py'
    sp=importlib.util.spec_from_file_location('agg',p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
    checks=[]
    def check(name,got,want):
     assert got==want,(name,got,want)
     checks.append(dict(test=name,actual=got,expected=want,passed=True))
    for values,want in [([100,None,-1,0,300],200),([None,-3,0],None),([0,1],1),([True,False,100,float('nan'),float('inf')],100)]:
     check('positive_average '+str(values),m.positive_average(values),want)
     items=[dict(test_result_id=i,dimension_value=v,round_count=1) for i,v in enumerate(values)]
     for mode in ['case','round']:check('strategy '+mode+str(values),m.SimpleAverageStrategy().aggregate(items,denominator_mode=mode),want)
    check('比例仍统计0失败',m.PassRateStrategy().aggregate([dict(test_result_id=i,dimension_value=v,round_count=1) for i,v in enumerate([1,0,None])]),50)
    # Execute the real round-value extraction without importing the database/application.
    p=root/'Intelligent-Audio-TEST/backend/utils/report/report_utils.py';tree=ast.parse(p.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ReportUtils');fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_get_round_values');fn.decorator_list=[]
    from types import SimpleNamespace
    stub=SimpleNamespace(_resolve_exclude_rounds=lambda *args:set());ns=dict(positive_average_values=m.positive_average_values,ReportUtils=stub)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(p),'exec'),ns)
    result=SimpleNamespace(id=1)
    for values,want in [([100,None,-1,0,300],[100,300]),([-1,0],[])]:
     rows={1:[dict(id=2,round_number=i,value=v) for i,v in enumerate(values)]}
     check('真实逐轮提取 '+str(values),ns['_get_round_values'](result,'latency',999,rows,{'latency':2}),want)
    # Compile all edited files; latency averages must follow the same policy.
    p=root/'eval_server/app/services/calculators/xiaoyi_metrics/interruptibility/full_timeline_judge.py';sp=importlib.util.spec_from_file_location('j',p);j=importlib.util.module_from_spec(sp);sp.loader.exec_module(j)
    check('完整时间线时延平均过滤',j._stats([None,-150,0,100,300])['avg_ms'],200)
    check('原始负数最小值仍保留',j._stats([-150,0,100])['min_ms'],-150)
    check('无正时延返回空',j._stats([None,-150,0])['avg_ms'],None)
