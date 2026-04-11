import re
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# [수정 1] 폰트 안전장치: 맑은 고딕 로드 실패 시 기본 폰트로 대체하여 크래시 방지
font_name = 'MalgunGothic'
try:
    pdfmetrics.registerFont(TTFont('MalgunGothic', 'C:/Windows/Fonts/malgun.ttf'))
except: 
    font_name = 'Helvetica' # 맑은 고딕이 없을 경우 영문 기본 폰트 사용

class PDFGenerator:
    @staticmethod
    def save_to_pdf(text, path):
        doc = SimpleDocTemplate(
            path, pagesize=(210 * mm, 297 * mm),
            rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm
        )
        styles = getSampleStyleSheet()
        # 폰트 변수 적용
        normal_style = ParagraphStyle('KNormal', fontName=font_name, fontSize=10, leading=14, spaceAfter=6, wordWrap='CJK')
        list_style = ParagraphStyle('KList', parent=normal_style, leftIndent=15, firstLineIndent=-5)
        
        story = []
        
        # [수정 2] AI가 자주 쓰는 **굵은 글씨** 마크다운을 PDF용 <b> 태그로 변환
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        
        lines = text.split('\n')
        table_data = []
        is_table = False

        for line in lines:
            line = line.strip()
            if line.startswith('|'):
                if re.match(r'^[|\-\s]+$', line): continue
                row = [cell.strip() for cell in line.split('|') if cell.strip()]
                if row:
                    table_data.append([Paragraph(cell, normal_style) for cell in row])
                    is_table = True
                continue
            else:
                if is_table and table_data:
                    col_widths = [doc.width/len(table_data[0])] * len(table_data[0]) if table_data[0] else None
                    t = Table(table_data, hAlign='LEFT', colWidths=col_widths)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey), ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('FONTNAME', (0, 0), (-1, -1), font_name), # 폰트 변수 적용
                        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ]))
                    story.append(t)
                    story.append(Spacer(1, 10))
                    table_data = []
                    is_table = False

            if not line:
                story.append(Spacer(1, 4))
                continue
            
            if line.startswith('### '): story.append(Paragraph(f"<br/><font size='12' color='#2c3e50'><b>{line[4:]}</b></font>", normal_style))
            elif line.startswith('## '): story.append(Paragraph(f"<br/><font size='14' color='#1a1a1a'><b>{line[3:]}</b></font>", normal_style))
            elif line.startswith('# '): story.append(Paragraph(f"<br/><font size='18' color='#000000'><b>{line[2:]}</b></font>", normal_style))
            elif line.startswith('- ') or line.startswith('* '): story.append(Paragraph(f"• {line[2:]}", list_style))
            else: story.append(Paragraph(line, normal_style))

        if table_data: 
            # 마지막 테이블 스타일 적용 (버그 방지)
            t = Table(table_data, hAlign='LEFT')
            t.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTNAME', (0, 0), (-1, -1), font_name),
            ]))
            story.append(t)
            
        doc.build(story)