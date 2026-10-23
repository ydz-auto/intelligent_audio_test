# -*- coding: utf-8 -*-
import time
import int1483_helpers as H
d = H.driver()
try:
    print('login', H.login(d))
    d.get(H.BASE + '/AlgorithmConfig')
    time.sleep(6)
    print('URL', d.current_url)
    print('TEXT', H.body_text(d)[:600])
    H.shot(d, 'debug_state')
    print('LOG', [(e['url'], e['status']) for e in H.fetch_log(d, '/algorithm')][:10])
finally:
    d.quit()
