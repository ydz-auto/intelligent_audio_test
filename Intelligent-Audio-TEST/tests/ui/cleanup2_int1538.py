import sys, os, time
sys.path.insert(0, r'D:\00_user_data\multica_workspaces\intelligent-95ba6a12369f\int-1538-93ea67985d4d\worktree\Intelligent-Audio-TEST\tests\ui')
import int1538_lib as L
OUT={}
d=L.driver()
try:
    L.login(d); d.get(L.BASE+'/testcases'); time.sleep(4)
    st,p,_=L.api_json(d,'/testcases?page=1&per_page=200&only_deleted=1&keyword=' + '接线测试_INT1538')
    items=((p or {}).get('data') or {}).get('items') or []
    OUT['before']=[(x['id'],x['name']) for x in items]
    for x in items:
        r=L.api_json(d,'/testcases/'+x['id']+'/purge','DELETE')
        OUT.setdefault('purge',[]).append((x['id'],r[0],r[2][:100]))
    st,p,_=L.api_json(d,'/testcases?page=1&per_page=200&only_deleted=1&keyword=' + '接线测试_INT1538')
    OUT['after']=[(x['id'],x['name']) for x in (((p or {}).get('data') or {}).get('items') or [])]
    st,p,_=L.api_json(d,'/testcases?page=1&per_page=1')
    OUT['total']=((p or {}).get('data') or {}).get('total')
finally:
    L.save_evidence('cleanup2_evidence', OUT); d.quit()
