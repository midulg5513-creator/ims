# -*- coding: utf-8 -*-
from pathlib import Path
import pandas as pd
import numpy as np
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

HERE=Path(__file__).resolve().parent
T0=HERE/'t0_analysis'; POS=HERE/'positive_posts_analysis'

def csv(name, folder=T0): return pd.read_csv(folder/name)
def set_cell(cell, text, bold=False):
    cell.text=str(text); cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for p in cell.paragraphs:
        p.paragraph_format.space_after=Pt(0)
        for r in p.runs: r.font.name='宋体'; r.font.size=Pt(9); r.bold=bold
def shade(cell, fill):
    tcPr=cell._tc.get_or_add_tcPr(); shd=OxmlElement('w:shd'); shd.set(qn('w:fill'),fill); tcPr.append(shd)
def add_table(doc, headers, rows):
    t=doc.add_table(rows=1, cols=len(headers)); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.style='Table Grid'
    for i,h in enumerate(headers): set_cell(t.rows[0].cells[i],h,True); shade(t.rows[0].cells[i],'E8EEF5')
    for row in rows:
        cells=t.add_row().cells
        for i,v in enumerate(row): set_cell(cells[i],v)
    return t
def para(doc,text='',style=None,bold=False):
    p=doc.add_paragraph(style=style); r=p.add_run(text); r.bold=bold; r.font.name='宋体'; r.font.size=Pt(10.5); return p

def main():
    ind=csv('t0_by_industry.csv'); acc=csv('t0_by_account_type.csv'); med=csv('t0_by_media_type.csv')
    hyp=pd.read_csv(POS/'hypothesis_validation.csv')
    audit=pd.read_csv(POS/'integration_audit.csv'); n=int(audit.loc[audit.item=='positive_repost_posts','value'].iloc[0]); integrated=int(audit.loc[audit.item=='unique_integrated_posts','value'].iloc[0]); removed=int(audit.loc[audit.item=='zero_repost_posts_removed','value'].iloc[0])
    fit=pd.read_csv(POS/'positive_model_fit.csv'); r2=float(fit.loc[fit.metric=='r_squared','value'].iloc[0]); ar2=float(fit.loc[fit.metric=='adj_r_squared','value'].iloc[0])
    def hv(code):
        x=hyp[hyp.hypothesis==code].iloc[0]; return f"系数{float(x.estimate):.3f}，p={float(x.p_value):.3f}，{x.conclusion}"
    md=f'''# 微博广告帖子影响力研究报告

## 摘要

本文参考范例报告的“理论假设—数据说明—回归分析—结论与建议”结构，整合项目中的历史帖子与第二阶段关键词采集数据，按 `post_id` 去重后得到 {integrated} 条帖子。按照研究要求，进一步删除转发数为0的帖子，保留 {n} 条正转发帖子。研究因变量为 `ln(转发数)`，重点考察粉丝规模、文本长度、图片数量、视频、促销词密度和抽奖机制等因素。HC3稳健标准误回归的R²为{r2:.3f}，调整R²为{ar2:.3f}。

结果显示，在已经获得至少一次转发的帖子中，粉丝规模和抽奖机制与转发量呈显著正相关；文本长度在本轮扩展样本中仅接近显著。图片、视频和促销词密度没有得到稳健支持。由于零转发帖子被删除，本文不解释“获得至少一次转发的概率”，所有结论均为条件相关关系。

## 一、研究假设

H1a：粉丝规模越大，正转发帖子中的转发量越高。

H1b：作者历史互动质量越高，转发量越高。

H2：文本长度、图片数量和视频等内容丰富度与转发量正相关，文本长度同时检验二次项。

H3：促销词密度和硬广告标识与转发量负相关。

H4：抽奖或福利机制与转发量正相关。

H5：不同诉求类型和媒体类型的核心影响因素存在差异。

## 二、数据来源与处理

数据来自微博移动端公开接口和项目既有CSV文件。整合 `stage2_posts.csv`、`posts.csv` 和 `stata_data.csv`，并按帖子ID去重。合并前共1,394条记录，去重后{integrated}条；删除{removed}条零转发帖子后，最终研究样本为{n}条。辅助合并了T0快照、评论、帖子详情和作者资料字段，但不把同期评论和点赞作为普通解释变量，以避免明显的同时性问题。

第二阶段样本当前为454条：美妆63、食品77、服饰72、数码家电84、汽车72、生活服务86；媒体类型为视频316、图片93、其他45。样本由关键词配额搜索获得，不是微博总体的概率样本。

## 三、变量与模型

因变量为 `ln(reposts+1)`。核心解释变量包括 `log_followers`、文本长度及其平方项、图片数、视频虚拟变量、抽奖虚拟变量、促销词密度和硬广告标识。模型控制数据来源差异，并使用HC3稳健标准误：

`ln(reposts_i) = β0 + β1 log_followers_i + β2 text_len_i + β3 text_len_i² + β4 images_i + β5 video_i + β6 lottery_i + β7 promo_density_i + controls_i + ε_i`

由于样本仅保留正转发帖子，该模型是条件转发量模型，不是完整的两部传播模型。

## 四、描述性统计

### 行业分布
'''
    for _,x in ind.iterrows(): md+=f"- {x['industry']}：{int(x['n'])}条，平均转发{float(x['mean_reposts']):.2f}，零转发比例{float(x['zero_share']):.1%}\n"
    md+='''
### 账号和媒体分布

品牌官方账号的平均转发明显高于KOL和媒体/其他账号；图片帖数量增加后仍低于视频帖，其他媒体样本最少。描述性均值受到少数高转发帖影响，应结合对数模型解释。

## 五、假设检验结果

'''
    for code,label in [('H1a','粉丝规模'),('H2_text','文本长度'),('H2_text_sq','文本长度二次项'),('H2_images','图片数量'),('H2_video','视频'),('H3_promo','促销词密度'),('H4_lottery','抽奖机制'),('H3_hard_ad','硬广告')]: md+=f"- {label}（{code}）：{hv(code)}。\n"
    md+='''- H1b：无法检验。当前整合数据没有每条目标帖发布前的严格历史互动特征。
- H4的“获得至少一次转发概率”版本：无法检验，因为零转发帖子已按要求删除。
- H5：仅作探索性说明。当前媒体和诉求类别分布不平衡，不能用“一个组显著、另一个组不显著”替代正式交互项检验。

## 六、结果解释

粉丝规模的正向结果与社会影响理论一致：在已经获得传播的帖子中，账号触达基础越大，转发量通常越高。抽奖机制的正向结果说明福利设计可能强化转发动机，但抽奖变量仍需更大样本和人工编码复核。文本长度、图片和视频未显示稳定关系，说明“形式丰富”不必然等于更高传播，内容质量、受众匹配和账号差异可能更重要。促销词密度不显著，不能据此断言促销词一定降低转发。

## 七、运营建议

第一，优先选择粉丝基础和历史活跃度较高的账号发布广告。第二，抽奖机制可以作为提高已有传播帖转发量的候选策略，但应控制活动规则、奖品价值和合规风险。第三，不要单纯追求文字更长、图片更多或视频化，应进一步编码图片质量、视频时长、内容类型和信息匹配度。第四，后续研究保留零转发帖子，用Logit或hurdle模型区分“是否获得转发”和“获得转发后的数量”。

## 八、局限性

本研究存在非概率配额抽样、媒体类型失衡、正转发筛选造成的选择性、自动广告和诉求识别误差，以及同期观察时距差异等问题。结果不能外推为微博全部广告帖的无偏总体效应，也不应使用“导致”“提升”等因果措辞。硬广告样本极少，相关系数不稳定；作者历史特征和图片/视频质量变量仍需补充。

## 九、结论

当前证据支持：在已经获得至少一次转发的微博广告帖中，粉丝规模和抽奖机制与更高转发量相关。文本长度只有边缘证据，图片、视频、促销词密度和硬广告未获得稳定支持。该结论适用于本项目的正转发样本，后续若要回答完整的广告传播机制问题，应恢复零转发样本并采用两部模型。

## 附录：可复核文件

- `positive_posts_analysis/positive_repost_posts.csv`
- `positive_posts_analysis/hypothesis_validation.csv`
- `positive_posts_analysis/hypothesis_regression_summary.txt`
- `t0_analysis/t0_by_industry.csv`
- `t0_analysis/t0_by_media_type.csv`
'''
    (HERE/'微博广告帖子影响力研究报告.md').write_text(md,encoding='utf-8')
    doc=Document(); sec=doc.sections[0]; sec.top_margin=Inches(0.8); sec.bottom_margin=Inches(0.8); sec.left_margin=Inches(0.9); sec.right_margin=Inches(0.9)
    styles=doc.styles; styles['Normal'].font.name='宋体'; styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'),'宋体'); styles['Normal'].font.size=Pt(10.5)
    for nm,size,color in [('Title',22,'17365D'),('Heading 1',16,'2E74B5'),('Heading 2',13,'1F4D78')]:
        st=styles[nm]; st.font.name='黑体'; st._element.rPr.rFonts.set(qn('w:eastAsia'),'黑体'); st.font.size=Pt(size); st.font.color.rgb=RGBColor.from_string(color)
    p=doc.add_paragraph(style='Title'); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.add_run('微博广告帖子影响力研究报告')
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.add_run('——基于关键词采集与正转发样本的实证分析').italic=True
    para(doc,'摘要', 'Heading 1'); para(doc, f'本文整合项目既有数据和第二阶段关键词采集数据，按帖子ID去重后得到{integrated}条帖子，删除零转发帖子后保留{n}条正转发帖子。结果显示，在已经获得至少一次转发的帖子中，粉丝规模和抽奖机制与转发量显著正相关；文本长度仅接近显著，图片、视频和促销词密度未得到稳定支持。模型R²为{r2:.3f}，调整R²为{ar2:.3f}。由于零转发帖子被删除，本文不解释获得转发概率，结论均为条件相关关系。')
    para(doc,'一、研究假设','Heading 1'); para(doc,'H1a：粉丝规模越大，正转发帖子中的转发量越高。H1b：作者历史互动质量越高，转发量越高。H2：文本长度、图片数量和视频与转发量正相关，并检验文本长度二次项。H3：促销词密度和硬广告标识与转发量负相关。H4：抽奖或福利机制与转发量正相关。H5：不同诉求类型和媒体类型的影响因素存在差异。')
    para(doc,'二、数据来源与样本处理','Heading 1'); para(doc,f'数据来自微博移动端接口和项目既有CSV文件。合并stage2_posts、posts和stata_data后按post_id去重：合并记录1,394条，去重后{integrated}条，删除零转发帖子{removed}条，最终样本{n}条。第二阶段当前样本454条，包含视频316条、图片93条、其他45条。关键词配额样本不是微博总体概率样本。')
    para(doc,'三、变量与模型','Heading 1'); para(doc,'因变量为ln(reposts+1)，核心变量包括粉丝规模、文本长度及平方项、图片数量、视频、抽奖、促销词密度和硬广告标识。模型控制数据来源差异，采用HC3稳健标准误。由于仅保留正转发帖子，模型解释的是正转发条件下的数量差异。')
    para(doc,'四、描述性统计','Heading 1'); add_table(doc,['行业','样本数','平均转发','零转发比例'],[[x['industry'],int(x['n']),f"{float(x['mean_reposts']):.2f}",f"{float(x['zero_share']):.1%}"] for _,x in ind.iterrows()])
    para(doc,'五、假设检验结果','Heading 1'); add_table(doc,['假设','估计结果','结论'],[[code,hv(code).split('，')[0]+'，'+hv(code).split('，')[1],hyp[hyp.hypothesis==code].iloc[0]['conclusion']] for code in ['H1a','H2_text','H2_text_sq','H2_images','H2_video','H3_promo','H4_lottery','H3_hard_ad']])
    para(doc,'六、结果解释与运营建议','Heading 1'); para(doc,'粉丝规模和抽奖机制是当前正转发样本中最稳定的相关因素。建议优先选择具有较大粉丝基础和活跃受众的账号，并谨慎使用抽奖机制。文字、图片和视频形式不能单独替代内容质量；后续应补充图片质量、视频时长和诉求类型编码。')
    para(doc,'七、研究局限与结论','Heading 1'); para(doc,'本研究受到非概率抽样、媒体类型失衡、正转发筛选、自动识别误差和观察时距差异限制。结论不能外推为微博总体因果效应。当前证据支持粉丝规模和抽奖机制与正转发帖转发量相关，其他假设暂未获得稳定支持。')
    doc.add_paragraph('数据与代码：positive_posts_analysis/；t0_analysis/').italic=True
    doc.save(HERE/'微博广告帖子影响力研究报告.docx')
    print('[done] report markdown and docx')
if __name__=='__main__': main()
