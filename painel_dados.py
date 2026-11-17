"""Gera os arquivos do painel (saidas/painel/*.json) a partir das saídas do modelo.

Uso: python painel_dados.py [pasta_das_saidas] [pasta_de_destino]
"""
import pandas as pd, numpy as np, json
import sys
S=(sys.argv[1] if len(sys.argv)>1 else 'saidas').rstrip('/')+'/'; O=(sys.argv[2] if len(sys.argv)>2 else 'saidas/painel').rstrip('/')+'/'
import os; os.makedirs(O,exist_ok=True)
rho=json.load(open(S+'resumo.json'))['rho']
r1=lambda x: np.round(x,1)
base=pd.read_csv(S+'base_unidades.csv',parse_dates=['mes'])
prev=pd.read_csv(S+'previsao_producao.csv',parse_dates=['mes'])
proj=pd.read_csv(S+'previsao_projetos.csv',parse_dates=['mes'])
ult=base.mes.max()
# --- Brasil
hist=base.groupby('mes').petroleo_bpd.sum()/1e3
def banda(g, lo, hi):
    w_lo=(g.p50-g[lo]); w_hi=(g[hi]-g.p50)
    f=lambda w: np.sqrt((w**2).sum()*(1-rho)+rho*w.sum()**2)
    return f(w_lo), f(w_hi)
rows=[]
for m,g in prev.groupby('mes'):   # p10/p50/p90 já incluem as plataformas novas
    lo,hi=banda(g,'p10','p90'); p50=g.p50.sum()
    rows.append(dict(mes=m,p50=p50/1e3,p10=(p50-lo)/1e3,p90=(p50+hi)/1e3))
fc=pd.DataFrame(rows)
h=hist[hist.index>='2018-01-01'].reset_index().rename(columns={'petroleo_bpd':'realizado'})
ponte=pd.DataFrame([dict(mes=ult,p10=hist[ult],p50=hist[ult],p90=hist[ult])])
bm=pd.concat([h,ponte,fc]).groupby('mes').first().reset_index()
bm['mes']=bm.mes.dt.strftime('%Y-%m-%d')
for c in ['realizado','p10','p50','p90']: bm[c]=r1(bm[c])
bm.to_csv(O+'brasil_mensal.csv',index=False)
# --- unidades
m12h=base[base.mes>ult-pd.DateOffset(months=12)].groupby('unidade').petroleo_bpd.mean()/1e3
pm=sorted(prev.mes.unique())[:12]
tot=prev.assign(t=prev.p50)
m12p=tot[tot.mes.isin(pm)].groupby('unidade').t.mean()/1e3
rr=pd.read_csv(S+'previsao_receita_royalties.csv',parse_dates=['mes']); rr12=rr[rr.mes.isin(pm)].groupby('unidade')[['receita_p50','royalties_p50']].sum()/1e9
op=prev.groupby('unidade')[['operador','bacia']].first()
u=pd.DataFrame({'ult12':m12h,'prox12':m12p}).join(rr12).join(op).dropna(subset=['prox12'])
u['var_pct']=(u.prox12/u.ult12-1)*100
u=u.sort_values('prox12',ascending=False).head(15).reset_index().rename(columns={'index':'unidade'})
u=u[['unidade','operador','bacia','ult12','prox12','var_pct','receita_p50','royalties_p50']].rename(columns={'receita_p50':'receita12','royalties_p50':'royalties12'})
for c in ['ult12','prox12','var_pct']: u[c]=r1(u[c])
for c in ['receita12','royalties12']: u[c]=np.round(u[c],2)
u.to_csv(O+'unidades_resumo.csv',index=False)
top=u.unidade.tolist()
hu=base[(base.unidade.isin(top))&(base.mes>='2023-01-01')].assign(realizado=lambda d:d.petroleo_bpd/1e3)[['unidade','mes','realizado']]
fu=prev[prev.unidade.isin(top)].copy()
for c in ['p10','p50','p90']: fu[c]=fu[c]/1e3
lastu=base[(base.unidade.isin(top))&(base.mes==ult)].assign(p10=lambda d:d.petroleo_bpd/1e3,p50=lambda d:d.petroleo_bpd/1e3,p90=lambda d:d.petroleo_bpd/1e3)[['unidade','mes','p10','p50','p90']]
um=pd.concat([hu,lastu,fu[['unidade','mes','p10','p50','p90']]]).groupby(['unidade','mes']).first().reset_index()
um['mes']=um.mes.dt.strftime('%Y-%m-%d')
for c in ['realizado','p10','p50','p90']: um[c]=r1(um[c])
um.to_csv(O+'unidades_mensal.csv',index=False)
# --- empresas
lh=pd.read_csv(S+'producao_liquida_historica.csv',parse_dates=['mes']); lp=pd.read_csv(S+'previsao_liquida_empresas.csv',parse_dates=['mes'])
e12h=lh[lh.mes>ult-pd.DateOffset(months=12)].groupby('empresa').oleo_liq.mean()/1e3
lp12=lp[lp.mes.isin(pm)]
e=pd.DataFrame({'ult12':e12h,'prox12':lp12.groupby('empresa').producao_liq.mean()/1e3,'receita12':lp12.groupby('empresa').receita_liq.sum()/1e9,'royalties12':lp12.groupby('empresa').royalties_liq.sum()/1e9})
e=e.drop(index=[i for i in e.index if i in('Outras','União (PPSA)')],errors='ignore').dropna().sort_values('prox12',ascending=False).head(10)
e['var_pct']=(e.prox12/e.ult12-1)*100
e=e.reset_index().rename(columns={'index':'empresa'})[['empresa','ult12','prox12','var_pct','receita12','royalties12']]
for c in ['ult12','prox12','var_pct']: e[c]=r1(e[c])
for c in ['receita12','royalties12']: e[c]=np.round(e[c],2)
e.to_csv(O+'empresas_resumo.csv',index=False)
te=e.empresa.tolist()
eh=lh[(lh.empresa.isin(te))&(lh.mes>='2023-01-01')].assign(realizado=lambda d:d.oleo_liq/1e3)[['empresa','mes','realizado']]
ep=lp[lp.empresa.isin(te)].assign(previsto=lambda d:d.producao_liq/1e3)[['empresa','mes','previsto']]
el=lh[(lh.empresa.isin(te))&(lh.mes==ult)].assign(previsto=lambda d:d.oleo_liq/1e3)[['empresa','mes','previsto']]
em=pd.concat([eh,el,ep]).groupby(['empresa','mes']).first().reset_index(); em['mes']=em.mes.dt.strftime('%Y-%m-%d')
for c in ['realizado','previsto']: em[c]=r1(em[c])
em.to_csv(O+'empresas_mensal.csv',index=False)
# --- royalties e mercado
b=pd.read_csv(S+'previsao_brasil.csv',parse_dates=['mes']); 
ro=pd.DataFrame({'mes':b.mes.dt.strftime('%Y-%m-%d')})
for c in ['royalties_p10','royalties_p50','royalties_p90','receita_p50']: ro[c]=np.round(b[c]/1e9,2)
ro.to_csv(O+'royalties_mensal.csv',index=False)
mk=pd.read_csv(S+'cenario_mercado.csv'); mk[['brent_base','brent_p10','brent_p90']]=mk[['brent_base','brent_p10','brent_p90']].round(1); mk['ptax_p50']=mk.ptax_p50.round(2)
mk[['mes','brent_base','brent_p10','brent_p90','ptax_p50']].to_csv(O+'mercado.csv',index=False)
# --- projetos
pj=proj.copy(); pj['mes']=pd.to_datetime(pj.mes).dt.strftime('%Y-%m-%d')
for c in ['p10','p50','p90']: pj[c]=r1(pj[c]/1e3)
pj[['instalacao','mes','p10','p50','p90']].to_csv(O+'projetos_mensal.csv',index=False)
# --- acurácia
t=pd.read_csv(S+'torneio.csv'); t=t[t.periodo.str.contains('2022')].copy()
t=t[~t.metodo.str.contains('Arps poço')]
a=pd.DataFrame({'metodo':t.metodo,'wape_pct':r1(t['WAPE por unidade']*100),'erro_carteira_pct':r1(t['Erro da carteira']*100),'vies_pct':r1(t['Viés']*100)}).sort_values('wape_pct')
a.to_csv(O+'acuracia.csv',index=False)
# --- kpis
p12=fc.p50.iloc[:12].mean(); h12=hist[hist.index>ult-pd.DateOffset(months=12)].mean()
roy=b.royalties_p50.iloc[:12].sum()/1e9; rec=b.receita_p50.iloc[:12].sum()/1e9
pjl=proj.groupby('mes').p50.sum()/1e3
fin=a[a.metodo.str.startswith('Modelo final')].iloc[0]; ing=a[a.metodo.str.startswith('Ingênuo (')].iloc[0]
kp=pd.DataFrame([
 dict(kpi='producao',valor=np.round(p12),ref=np.round(h12),var_pct=r1((p12/h12-1)*100),baixo=np.round(fc.p10.iloc[:12].mean()),alto=np.round(fc.p90.iloc[:12].mean())),
 dict(kpi='royalties',valor=r1(roy),ref=None,var_pct=None,baixo=r1(b.royalties_p10.iloc[:12].sum()/1e9),alto=r1(b.royalties_p90.iloc[:12].sum()/1e9)),
 dict(kpi='receita',valor=np.round(rec),ref=None,var_pct=None,baixo=np.round(b.receita_p10.iloc[:12].sum()/1e9),alto=np.round(b.receita_p90.iloc[:12].sum()/1e9)),
 dict(kpi='plataformas',valor=np.round(pjl.iloc[-1]),ref=None,var_pct=None,baixo=None,alto=None),
 dict(kpi='erro',valor=fin.wape_pct,ref=ing.wape_pct,var_pct=None,baixo=None,alto=None),
 dict(kpi='brent',valor=r1(mk.brent_base.iloc[:12].mean()),ref=None,var_pct=None,baixo=None,alto=None),
])
kp.to_csv(O+'kpis.csv',index=False)
meta=dict(ultimo_mes=str(ult.date()),fim=str(fc.mes.max().date()))
print(meta); print(kp.to_string()); print(u.head(5).to_string()); print(e.to_string())

# --- simulador: por empresa e mês, com a parte que vem das plataformas novas de Búzios
pes=pd.read_csv(S+'pesos_unidade_empresa.csv').query("unidade=='BÚZIOS'").set_index('empresa').peso   # parte de cada empresa em Búzios (mix dos últimos 3 meses × participação)
bz=rr[rr.unidade=='BÚZIOS'].set_index('mes'); pjt=proj.groupby('mes').p50.sum()/1e3
rec_bbl=(bz.receita_p50/1e9)/(bz.producao_p50/1e3); roy_bbl=(bz.royalties_p50/1e9)/(bz.producao_p50/1e3)
sim=[]
tt=pd.DataFrame({'prod':prev.groupby('mes').p50.sum()/1e3,'receita':b.set_index('mes').receita_p50/1e9,'royalties':b.set_index('mes').royalties_p50/1e9})
for emp in ['Total']+te:
    d=tt if emp=='Total' else lp[lp.empresa==emp].set_index('mes').assign(prod=lambda x:x.producao_liq/1e3,receita=lambda x:x.receita_liq/1e9,royalties=lambda x:x.royalties_liq/1e9)
    w=1.0 if emp=='Total' else float(pes.get(emp,0.0))
    for m in d.index:
        sim.append(dict(empresa=emp,mes=m.strftime('%Y-%m-%d'),prod=round(d.loc[m,'prod'],2),receita=round(d.loc[m,'receita'],4),royalties=round(d.loc[m,'royalties'],4),
                        prod_proj=round(w*pjt[m],2),rec_bbl=round(rec_bbl[m],6),roy_bbl=round(roy_bbl[m],6)))
pd.DataFrame(sim).to_csv(O+'sim_empresas.csv',index=False)
# --- sócios, campo a campo (parte de cada empresa = mix dos subcampos × participação no contrato)
w=pd.read_csv(S+'pesos_unidade_empresa.csv'); ope=prev.groupby('unidade').operador.first()
hu12=base[base.mes>ult-pd.DateOffset(months=12)].groupby('unidade').petroleo_bpd.mean()/1e3
pu12=prev[prev.mes.isin(pm)].groupby('unidade').p50.mean()/1e3
ru12=rr[rr.mes.isin(pm)].groupby('unidade').receita_p50.sum()/1e9
sc=w.assign(operador=w.unidade.map(ope),part_pct=w.peso*100,ult12=w.unidade.map(hu12).fillna(0)*w.peso,prox12=w.unidade.map(pu12).fillna(0)*w.peso,receita12=w.unidade.map(ru12).fillna(0)*w.peso)
dep=[]
pr=pd.read_csv(S+'previsto_realizado.csv.gz',parse_dates=['mes'])
for emp in te:
    g=sc[sc.empresa==emp]; t=g.prox12.sum()
    x=pr[pr.h==6].merge(w[w.empresa==emp][['unidade','peso']],on='unidade'); x=(x[['previsto','ingenuo','real']].multiply(x.peso,axis=0)).groupby(x.mes).sum().tail(12)
    dep.append(dict(empresa=emp,prox12=round(t,1),petrobras_pct=round(g[g.operador=='Petrobras'].prox12.sum()/t*100,1),propria_pct=round(g[g.operador==emp].prox12.sum()/t*100,1),
                    erro6=round(((x.previsto-x.real).abs()/x.real).mean()*100,1),erro6_ingenuo=round(((x.ingenuo-x.real).abs()/x.real).mean()*100,1)))
dep=pd.DataFrame(dep); dep['outros_pct']=(100-dep.petrobras_pct-dep.propria_pct).round(1).clip(lower=0)
# a Petrobras opera 100% da própria produção: os dois percentuais coincidem
dep.to_csv(O+'dependencia.csv',index=False)
sc=sc[sc.empresa.isin(te)&(sc.prox12>=0.5)].copy(); sc['var_pct']=np.where(sc.ult12>0.05,(sc.prox12/sc.ult12-1)*100,np.nan)
for c in ['part_pct','ult12','prox12','var_pct']: sc[c]=r1(sc[c])
sc['receita12']=sc.receita12.round(2)
sc.sort_values(['empresa','prox12'],ascending=[True,False])[['empresa','unidade','operador','part_pct','ult12','prox12','var_pct','receita12']].to_csv(O+'socios_campos.csv',index=False)
# --- previsto × realizado (previsões publicadas quando existirem; antes disso, teste retroativo)
tp=pr[pr.h.isin([1,3,6,12])].groupby(['mes','h']).agg(previsto=('previsto','sum'),ingenuo=('ingenuo','sum'),real=('real','sum'),fonte=('fonte',lambda x:x.mode().iat[0])).reset_index()
for c in ['previsto','ingenuo','real']: tp[c]=r1(tp[c]/1e3)
tp['mes']=tp.mes.dt.strftime('%Y-%m-%d'); tp.to_csv(O+'track_record.csv',index=False)
um=pr.mes.max(); p4=pr[pr.h.isin([1,3,6,12])]; top15=p4[p4.mes==um].groupby('unidade').real.sum().sort_values(ascending=False).head(15).index
p4=p4.assign(unidade=np.where(p4.unidade.isin(top15),p4.unidade,'Demais campos'))
g=p4.groupby(['unidade','h','mes'])[['previsto','real']].sum().reset_index()
u12=g[g.mes>um-pd.DateOffset(months=12)].assign(e=lambda d:(d.previsto-d.real).abs()).groupby(['unidade','h']).agg(e=('e','sum'),r=('real','sum'))
pc=g[g.mes==um].merge((u12.e/u12.r*100).rename('erro12').reset_index(),on=['unidade','h'])
pc['desvio']=pc.real-pc.previsto; pc['desvio_pct']=np.where(pc.previsto>0,(pc.real/pc.previsto-1)*100,np.nan)
for c in ['previsto','real','desvio']: pc[c]=r1(pc[c]/1e3)
for c in ['desvio_pct','erro12']: pc[c]=r1(pc[c])
pc['mes']=pc.mes.dt.strftime('%Y-%m-%d'); pc[['unidade','h','mes','previsto','real','desvio','desvio_pct','erro12']].to_csv(O+'pr_campos.csv',index=False)
# --- de onde vem o crescimento
d=pd.DataFrame({'ult12':hu12,'prox12':pu12}).fillna(0); d['delta']=d.prox12-d.ult12
tp6=d.delta.abs().sort_values(ascending=False).head(6).index
cr=pd.concat([d.loc[tp6],pd.DataFrame(d.drop(tp6).sum()).T.assign(unidade='Demais campos').set_index('unidade')]).rename_axis('unidade').reset_index()
for c in ['ult12','prox12','delta']: cr[c]=r1(cr[c])
cr.sort_values('delta',ascending=False).to_csv(O+'crescimento.csv',index=False)
# --- entrada em operação das plataformas
rp=pd.read_csv(S+'rampas_plataformas.csv',parse_dates=['inicio']); cv=pd.read_csv(S+'curva_rampa.csv')
cvo=pd.DataFrame({'mes':cv.k+1,'p10':r1(cv.f10*100),'p50':r1(cv.f50*100),'p90':r1(cv.f90*100)}); cvo=cvo[cvo.mes<=24]; cvo.to_csv(O+'curva_rampa.csv',index=False)
rn=rp[rp.nominal].copy()
ro=pd.DataFrame({'plataforma':rn.instalacao.str.replace('FPSO ','',regex=False).str.replace('PETROBRAS ','P-',regex=False).str.title().str.replace(' De ',' de ',regex=False).str.replace('Tamandare','Tamandaré',regex=False),'unidade':rn.unidade,'inicio':rn.inicio.dt.strftime('%Y-%m-%d'),
  'capacidade':r1(rn.capacidade/1e3),'meses_obs':rn.meses_obs,'meses_80':rn.meses_80,'pct_12':r1(rn.frac_12*100),'pico_pct':r1(rn.pico*100)}).sort_values('inicio',ascending=False)
ro.to_csv(O+'rampas.csv',index=False)
pre=rn[rn.unidade.isin(['BÚZIOS','MERO'])&(rn.meses_obs>=10)]; out=rn[~rn.unidade.isin(['BÚZIOS','MERO'])&(rn.meses_obs>=18)]
m80=int(cv.k[cv.f50>=0.8].iloc[0])+1
rs=pd.DataFrame([dict(grupo='todas',n=len(rp),meses_80=m80,pct_12=round(cv.f50.iloc[11]*100,1),acima_nominal=None),
  dict(grupo='buzios_mero',n=len(pre),meses_80=pre.meses_80.median(),pct_12=round(pre.frac_12.median()*100,1),acima_nominal=int((pre.pico>1).sum())),
  dict(grupo='outras',n=len(out),meses_80=None,pct_12=round(out.frac_12.median()*100,1),acima_nominal=int((out.pico>1).sum()))])
rs.to_csv(O+'rampa_resumo.csv',index=False)
kp=pd.concat([kp,pd.DataFrame([dict(kpi='plataformas12',valor=np.round(pjl.iloc[:12].mean()),ref=None,var_pct=None,baixo=None,alto=None)])]); kp.to_csv(O+'kpis.csv',index=False)
# --- aba Previsão: previsto × realizado + próximos meses + cenário, por empresa
pw=pd.read_csv(S+'pesos_unidade_empresa.csv')
emps=['Total']+te
W=pd.concat([pd.DataFrame({'unidade':prev.unidade.unique(),'empresa':'Total','peso':1.0}),pw[pw.empresa.isin(te)]],ignore_index=True)
# base do simulador por campo (cenário central): produção, receita, royalties e a parte das plataformas novas
su=rr[['unidade','mes','producao_p50','receita_p50','royalties_p50']].merge(prev[['unidade','mes','projetos_p50']],on=['unidade','mes'],how='left').fillna(0)
su=pd.DataFrame({'unidade':su.unidade,'mes':su.mes.dt.strftime('%Y-%m-%d'),'prod':(su.producao_p50/1e3).round(3),'proj':(su.projetos_p50/1e3).round(3),
                 'receita':(su.receita_p50/1e9).round(5),'royalties':(su.royalties_p50/1e9).round(5)})
su.to_csv(O+'sim_unidades.csv',index=False)
W[W.peso>0.0005].assign(peso=lambda d:d.peso.round(5)).to_csv(O+'pesos.csv',index=False)
# previsão central com faixa, por empresa
cen=[]
for emp in emps:
    w=W[W.empresa==emp].set_index('unidade').peso
    for m,g in prev[prev.unidade.isin(w.index)].groupby('mes'):
        ww=g.unidade.map(w).values; p50=(g.p50.values*ww).sum()
        lo=np.sqrt(((ww*(g.p50-g.p10).values)**2).sum()*(1-rho)+rho*((ww*(g.p50-g.p10).values).sum())**2)
        hi=np.sqrt(((ww*(g.p90-g.p50).values)**2).sum()*(1-rho)+rho*((ww*(g.p90-g.p50).values).sum())**2)
        cen.append(dict(empresa=emp,mes=m.strftime('%Y-%m-%d'),p10=round((p50-lo)/1e3,1),p50=round(p50/1e3,1),p90=round((p50+hi)/1e3,1)))
cen=pd.DataFrame(cen)
# receita e royalties: P50 = soma da parte da empresa em cada campo; faixa = incerteza de volume da empresa
# combinada com a incerteza de preço (comum a todos), tirada da simulação do Brasil: preço² = total² − volume²
br=pd.read_csv(S+'previsao_brasil.csv',parse_dates=['mes']).groupby('mes')[['receita_p10','receita_p50','receita_p90','royalties_p10','royalties_p50','royalties_p90']].sum()
vt=cen[cen.empresa=='Total'].assign(mes=lambda d:pd.to_datetime(d.mes)).set_index('mes')
for k in ['receita','royalties']:
    for lado,a,b in [('lo',k+'_p10',None),('hi',k+'_p90',None)]:
        tot=(1-br[a]/br[k+'_p50']).abs(); vol=(1-vt.p10/vt.p50) if lado=='lo' else (vt.p90/vt.p50-1)
        br[k+'_preco_'+lado]=np.sqrt(np.clip(tot**2-vol.reindex(br.index).fillna(0)**2,0,None))
din=[]
for emp in emps:
    w=W[W.empresa==emp].set_index('unidade').peso
    x=rr[rr.unidade.isin(w.index)].assign(w=lambda d:d.unidade.map(w))
    g=x.assign(receita=x.receita_p50*x.w,royalties=x.royalties_p50*x.w).groupby('mes')[['receita','royalties']].sum()
    c=cen[cen.empresa==emp].assign(mes=lambda d:pd.to_datetime(d.mes)).set_index('mes')
    vlo=(1-c.p10/c.p50); vhi=(c.p90/c.p50-1)
    for k in ['receita','royalties']:
        lo=np.sqrt(vlo**2+br[k+'_preco_lo'].reindex(c.index)**2); hi=np.sqrt(vhi**2+br[k+'_preco_hi'].reindex(c.index)**2)
        p50=g[k].reindex(c.index)/1e9
        c[k+'_p50']=p50.round(3); c[k+'_p10']=(p50*(1-lo)).round(3); c[k+'_p90']=(p50*(1+hi)).round(3)
    din.append(c.reset_index().assign(mes=lambda d:d.mes.dt.strftime('%Y-%m-%d')))
cen=pd.concat(din)
cen.to_csv(O+'central.csv',index=False)
# previsões passadas × realizado, por empresa e antecedência (participações atuais aplicadas ao passado)
pr=pd.read_csv(S+'previsto_realizado.csv.gz',parse_dates=['mes'])
pr=pr[pr.h.isin([1,3,6,12])]
hist=[]
for emp in emps:
    x=pr.merge(W[W.empresa==emp][['unidade','peso']],on='unidade')
    g=x.assign(previsto=x.previsto*x.peso,ingenuo=x.ingenuo*x.peso,real=x.real*x.peso).groupby(['mes','h']).agg(previsto=('previsto','sum'),ingenuo=('ingenuo','sum'),real=('real','sum'),fonte=('fonte',lambda z:z.mode().iat[0])).reset_index()
    g['empresa']=emp; hist.append(g)
hist=pd.concat(hist); hist=hist[hist.real>0]
# R$ por barril realizado de cada campo e mês (receita e royalties): o previsto em R$ = volume previsto × preço realizado
rh=pd.read_csv(S+'receita_historica.csv',parse_dates=['mes'])
pr2=pr.merge(rh,on=['unidade','mes'],how='left').fillna({'receita':0,'royalties':0})
pr2=pr2[pr2.real>0].assign(rb=lambda d:d.receita/d.real, yb=lambda d:d.royalties/d.real)
hm=[]
for emp in emps:
    x=pr2.merge(W[W.empresa==emp][['unidade','peso']],on='unidade')
    g=x.assign(receita_prev=x.previsto*x.rb*x.peso,receita_real=x.receita*x.peso,royalties_prev=x.previsto*x.yb*x.peso,royalties_real=x.royalties*x.peso)\
       .groupby(['mes','h'])[['receita_prev','receita_real','royalties_prev','royalties_real']].sum().reset_index()
    g['empresa']=emp; hm.append(g)
hm=pd.concat(hm)
for c in ['receita_prev','receita_real','royalties_prev','royalties_real']: hm[c]=(hm[c]/1e9).round(3)
hist=hist.merge(hm,on=['empresa','mes','h'],how='left')
for c in ['previsto','ingenuo','real']: hist[c]=(hist[c]/1e3).round(1)
hist['mes']=hist.mes.dt.strftime('%Y-%m-%d')
hist[['empresa','mes','h','previsto','ingenuo','real','fonte','receita_prev','receita_real','royalties_prev','royalties_real']].to_csv(O+'historico.csv',index=False)
# o mesmo previsto × realizado e a mesma previsão, campo a campo (100% do campo; a parte de cada empresa sai dos pesos)
hc=pr2.assign(receita_prev=pr2.previsto*pr2.rb,royalties_prev=pr2.previsto*pr2.yb)[['unidade','mes','h','previsto','ingenuo','real','receita_prev','receita','royalties_prev','royalties']]\
    .rename(columns={'receita':'receita_real','royalties':'royalties_real'})
for c in ['previsto','ingenuo','real']: hc[c]=(hc[c]/1e3).round(2)
for c in ['receita_prev','receita_real','royalties_prev','royalties_real']: hc[c]=(hc[c]/1e9).round(4)
hc['mes']=hc.mes.dt.strftime('%Y-%m-%d')
hc.sort_values(['unidade','h','mes']).to_csv(O+'hist_campos.csv',index=False)
cc=prev[['unidade','mes','p10','p50','p90']].merge(rr[['unidade','mes','receita_p10','receita_p50','receita_p90','royalties_p10','royalties_p50','royalties_p90']],on=['unidade','mes'],how='left').fillna(0)
for c in ['p10','p50','p90']: cc[c]=(cc[c]/1e3).round(2)
for c in ['receita_p10','receita_p50','receita_p90','royalties_p10','royalties_p50','royalties_p90']: cc[c]=(cc[c]/1e9).round(4)
cc['mes']=cc.mes.dt.strftime('%Y-%m-%d')
cc.to_csv(O+'central_campos.csv',index=False)
# campo a campo no último mês, só campos da empresa (100% do campo) — reaproveita pr_campos com a lista de campos de cada empresa
W[W.peso>0.0005][['empresa','unidade']].to_csv(O+'campos_empresa.csv',index=False)
# --- aba Royalties: municípios e estados (R$ milhões, por mês de recebimento)
if os.path.exists(S+'royalties_beneficiarios.csv'):
    rb=pd.read_csv(S+'royalties_beneficiarios.csv',parse_dates=['competencia','recebimento'])
    rr_=pd.read_csv(S+'royalties_beneficiarios_resumo.csv')
    for c_ in ['valor','p10','p90','lei','previsto6']:
        rb[c_]=(rb[c_]/1e6).round(2)
    rb['mes']=rb.recebimento.dt.strftime('%Y-%m-%d'); rb['competencia']=rb.competencia.dt.strftime('%Y-%m-%d')
    rb[['entidade','tipo','uf','mes','competencia','origem','valor','p10','p90','lei','previsto6']].to_csv(O+'royalties_benef.csv',index=False)
    def conf(r):
        e1=abs(r.erro_teste) if pd.notna(r.erro_teste) else 99; e2=r.erro6 if pd.notna(r.erro6) else 99
        return 'boa' if e1<=10 and e2<=15 else ('média' if e1<=25 and e2<=35 else 'baixa')
    rr_['confianca']=rr_.apply(conf,axis=1)
    rec=rb[rb.origem=='realizado'].groupby('entidade').mes.max()
    rr_['ult_mes']=rr_.entidade.map(rec)
    for c_ in ['ult12','prox12','lei12']: rr_[c_]=(rr_[c_]/1e6).round(1)
    for c_ in ['var_pct','erro6','erro_teste']: rr_[c_]=rr_[c_].round(1)
    rr_['dif_lei']=(rr_.lei12-rr_.prox12).round(1)
    rr_.to_csv(O+'royalties_resumo.csv',index=False)
# --- aba Premissas: o que move a receita (para o analista conferir a previsão)
from pathlib import Path
CFG=Path(__file__).resolve().parent/'config'
ph=pd.read_csv(S+'precos_historicos.csv',parse_dates=['mes']).set_index('mes')
mk=pd.read_csv(S+'cenario_mercado.csv',parse_dates=['mes']).set_index('mes')
bcfg=pd.read_csv(CFG/'brent_mensal.csv',comment='#',parse_dates=['mes']).set_index('mes')
rs=json.load(open(S+'resumo.json'))
# preços: Brent realizado e cenário com faixa; câmbio realizado e mediana simulada
pp=[]
for m in pd.date_range('2024-01-01',mk.index.max(),freq='MS'):
    real=bcfg.tipo.get(m)=='realizado'; fut=m in mk.index and not real
    pp.append(dict(mes=m.strftime('%Y-%m-%d'),
        brent_real=round(float(bcfg.brent_usd[m]),2) if real else (round(float(ph.anp_usd[m]/rs['k_preco_brent']),2) if m in ph.index and pd.notna(ph.anp_usd.get(m)) else None),
        brent_base=round(float(mk.brent_base[m]),2) if fut else None, brent_p10=round(float(mk.brent_p10[m]),2) if fut else None, brent_p90=round(float(mk.brent_p90[m]),2) if fut else None,
        ptax=round(float(ph.ptax[m]),4) if m in ph.index and pd.notna(ph.ptax.get(m)) else (round(float(mk.ptax_p50[m]),4) if m in mk.index else None),
        ptax_tipo='realizado' if m in ph.index and pd.notna(ph.ptax.get(m)) else 'mediana simulada'))
pd.DataFrame(pp).to_csv(O+'precos.csv',index=False)
# receita por empresa e mês: 12 meses realizados (volume ANP × preço) + 18 previstos (centro do modelo)
bu=pd.read_csv(S+'base_unidades.csv',parse_dates=['mes']); rh=pd.read_csv(S+'receita_historica.csv',parse_dates=['mes'])
meses_r=pd.date_range(ult-pd.DateOffset(months=11),ult,freq='MS')
re=[]
for emp in emps:
    w=W[W.empresa==emp].set_index('unidade').peso
    v=bu[bu.mes.isin(meses_r)&bu.unidade.isin(w.index)].assign(x=lambda d:d.petroleo_bpd*d.unidade.map(w)).groupby('mes').x.sum()
    r=rh[rh.mes.isin(meses_r)&rh.unidade.isin(w.index)].assign(a=lambda d:d.receita*d.unidade.map(w),b=lambda d:d.royalties*d.unidade.map(w)).groupby('mes')[['a','b']].sum()
    for m in meses_r:
        re.append(dict(empresa=emp,mes=m,origem='realizado',prod=v.get(m,0)/1e3,receita=r.a.get(m,0)/1e9,royalties=r.b.get(m,0)/1e9))
    c=cen[cen.empresa==emp]
    for _,x in c.iterrows():
        re.append(dict(empresa=emp,mes=pd.Timestamp(x.mes),origem='previsto',prod=x.p50,receita=x.receita_p50,royalties=x.royalties_p50))
re=pd.DataFrame(re)
re['dias']=re.mes.dt.days_in_month
fx=pd.Series({pd.Timestamp(p['mes']):p['ptax'] for p in pp}); bb=pd.Series({pd.Timestamp(p['mes']):(p['brent_real'] if p['brent_real'] is not None else p['brent_base']) for p in pp})
re['cambio']=re.mes.map(fx); re['brent']=re.mes.map(bb)
re['preco_rs']=re.receita*1e9/(re['prod']*1e3*re.dias); re['preco_usd']=re.preco_rs/re.cambio
for c_,n_ in [('prod',1),('receita',3),('royalties',3),('cambio',2),('brent',1),('preco_rs',0),('preco_usd',1)]: re[c_]=re[c_].round(n_)
re['mes']=re.mes.dt.strftime('%Y-%m-%d')
re[['empresa','mes','origem','prod','dias','brent','cambio','preco_usd','preco_rs','receita','royalties']].to_csv(O+'receita_meses.csv',index=False)
# premissas e fontes
pj=pd.read_csv(CFG/'projetos.csv',comment='#')
fut12=mk.index[:12]; bf=bcfg.reindex(fut12)
br=lambda x,n=2:f'{x:,.{n}f}'.replace(',','X').replace('.',',').replace('X','.')
fontes=[dict(ordem=1,premissa='Brent',valor=f"US$ {mk.brent_base.iloc[0]:.0f} em {mk.index[0]:%m/%Y} (realizado) → US$ {mk.brent_base.iloc[-1]:.0f} em {mk.index[-1]:%m/%Y}; média de 12 meses US$ {mk.brent_base.iloc[:12].mean():.0f}",
         fonte='Realizado: EIA/FRED (série MCOILBRENTEU). Cenário: STEO da EIA de out/2026. Faixa P10–P90: choques históricos de preço sorteados (Monte Carlo).'),
    dict(ordem=2,premissa='Câmbio',valor=f"R$ {br(ph.ptax.dropna().iloc[-1])} (último PTAX, {ph.ptax.dropna().index[-1]:%m/%Y}), sem tendência; a faixa vem de choques históricos",
         fonte='Banco Central (PTAX médio mensal).'),
    dict(ordem=3,premissa='Preço do petróleo de cada campo',valor=f"Brent × {br(rs['k_preco_brent'])} × fator do campo (qualidade do óleo) × câmbio",
         fonte=f"Preço de referência da ANP por campo, publicado até {rs['ultimo_preco_anp']}; depois disso, a relação média com o Brent."),
    dict(ordem=4,premissa='Gás natural',valor='Preço de referência recente de cada campo, mantido constante; volume na proporção gás/óleo dos últimos 12 meses',
         fonte='ANP (preço de referência do gás natural).'),
    dict(ordem=5,premissa='Royalties',valor=f"Receita × alíquota do campo (10% a 15%) × {br(rs['fator_calibracao'],3)}; erro médio de {br(rs['erro_calibracao_2022']*100,1)}% ao mês contra o arrecadado desde 2022",
         fonte='ANP (royalties distribuídos) e alíquotas dos contratos.'),
    dict(ordem=6,premissa='Produção',valor=f"Modelo LightGBM por grupo de campos, com teto de capacidade das plataformas; {prev.unidade.nunique()} grupos",
         fonte=f"ANP, produção por poço até {ult:%m/%Y}."),
    dict(ordem=7,premissa='Plataformas novas',valor='; '.join(f"{r.instalacao.split(' (')[0]}: 1º óleo entre {pd.Timestamp(r.inicio_cedo):%m/%Y} e {pd.Timestamp(r.inicio_tarde):%m/%Y}, {r.capacidade_bpd/1e3:.0f} mil bbl/d" for r in pj.itertuples()),
         fonte='Comunicados da Petrobras e imprensa especializada (conferido em 13/11/2026).'),
    dict(ordem=8,premissa='Parte de cada empresa',valor='Participação no contrato de cada campo, ajustada pelos acordos de individualização em vigor',
         fonte='ANP (Relação de Concessionários) e acordos de individualização da produção.')]
pd.DataFrame(fontes).to_csv(O+'fontes.csv',index=False)
# --- JSON {rows, meta} para o painel (cada arquivo leva o código que o gerou)
import os; os.makedirs(O,exist_ok=True)
codigo=open(__file__,encoding='utf-8').read()
entrada={'brasil_mensal':'base_unidades.csv, previsao_producao.csv, previsao_projetos.csv, resumo.json (rho)',
 'unidades_resumo':'base_unidades.csv, previsao_producao.csv, previsao_receita_royalties.csv',
 'unidades_mensal':'base_unidades.csv, previsao_producao.csv, previsao_projetos.csv',
 'empresas_resumo':'producao_liquida_historica.csv, previsao_liquida_empresas.csv',
 'empresas_mensal':'producao_liquida_historica.csv, previsao_liquida_empresas.csv',
 'royalties_mensal':'previsao_brasil.csv','mercado':'cenario_mercado.csv','projetos_mensal':'previsao_projetos.csv',
 'sim_empresas':'previsao_producao.csv, previsao_liquida_empresas.csv, previsao_brasil.csv, previsao_receita_royalties.csv, previsao_projetos.csv, pesos_unidade_empresa.csv',
 'sim_unidades':'previsao_receita_royalties.csv, previsao_producao.csv','pesos':'pesos_unidade_empresa.csv','central':'previsao_producao.csv, previsao_receita_royalties.csv, previsao_brasil.csv, pesos_unidade_empresa.csv, resumo.json (rho)','historico':'previsto_realizado.csv.gz, receita_historica.csv, pesos_unidade_empresa.csv','campos_empresa':'pesos_unidade_empresa.csv','acuracia':'torneio.csv','track_record':'previsto_realizado.csv.gz','pr_campos':'previsto_realizado.csv.gz','socios_campos':'pesos_unidade_empresa.csv, previsao_producao.csv, previsao_receita_royalties.csv, base_unidades.csv','dependencia':'pesos_unidade_empresa.csv, previsao_producao.csv, previsto_realizado.csv.gz','crescimento':'base_unidades.csv, previsao_producao.csv','curva_rampa':'curva_rampa.csv','rampas':'rampas_plataformas.csv','rampa_resumo':'rampas_plataformas.csv, curva_rampa.csv','kpis':'todos os arquivos acima','precos':'precos_historicos.csv, cenario_mercado.csv, config/brent_mensal.csv, resumo.json','receita_meses':'base_unidades.csv, receita_historica.csv, central (acima), precos (acima)','hist_campos':'previsto_realizado.csv.gz, receita_historica.csv','central_campos':'previsao_producao.csv, previsao_receita_royalties.csv','royalties_benef':'royalties_beneficiarios.csv (rodar_modelo.py → src/royalties_municipios.py)','royalties_resumo':'royalties_beneficiarios_resumo.csv','fontes':'config/brent_mensal.csv, config/projetos.csv, cenario_mercado.csv, precos_historicos.csv, resumo.json'}
os.makedirs(O+'json',exist_ok=True)
for n,src in entrada.items():
    d=pd.read_csv(O+n+'.csv')
    rows=json.loads(d.to_json(orient='records',force_ascii=False))
    meta=[{'label':'prep.py','value':codigo,'type':'code','lang':'python'},
          {'label':'Entrada','value':'Saídas do modelo petro-forecast (rodar_modelo.py) em saidas_reais/: '+src},
          {'label':'Dados até','value':'ANP produção por poço até set/2026; previsão out/2026–mar/2028'}]
    json.dump({'rows':rows,'meta':meta},open(O+'json/'+n+'.json','w',encoding='utf-8'),ensure_ascii=False)
