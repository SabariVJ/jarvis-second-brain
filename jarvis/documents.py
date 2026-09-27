"""Structured, local-only PDF generation and an integrity-checked artifact registry."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import uuid

_CENT=Decimal('0.01')
_MONEY_LIMIT=Decimal('1000000000')


def _decimal(value,label,minimum=Decimal('0'),maximum=_MONEY_LIMIT):
    try:number=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):raise ValueError(label+' must be a valid number') from None
    if not number.is_finite() or number<minimum or number>maximum:raise ValueError(label+' is outside the supported range')
    return number


class DocumentAutomation:
    def __init__(self,database,data_dir,clock=None):
        self.database=database;self.data_dir=Path(data_dir).resolve();self.generated_dir=(self.data_dir/'generated').resolve()
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _source_ids(self,source_ids):
        if source_ids is None:return []
        if not isinstance(source_ids,list) or len(source_ids)>30:raise ValueError('Choose at most 30 indexed source notes')
        result=[]
        for source_id in source_ids:
            if not isinstance(source_id,str) or len(source_id)>80:raise ValueError('Source reference is invalid')
            self.database.document(source_id)
            if source_id not in result:result.append(source_id)
        return result

    @staticmethod
    def missing_invoice_fields(data):
        missing=[]
        for side,label in (('seller','Your business'),('customer','Customer')):
            record=data.get(side) if isinstance(data.get(side),dict) else {}
            for key,human in (('name','name'),('address','address')):
                if not isinstance(record.get(key),str) or not record[key].strip():missing.append(f'{label} {human}')
        items=data.get('items') if isinstance(data.get('items'),list) else []
        if not items:missing.append('At least one line item')
        else:
            for index,item in enumerate(items[:30],1):
                if not isinstance(item,dict) or not str(item.get('description','')).strip():missing.append(f'Line {index} description')
                if not isinstance(item,dict) or item.get('quantity') in (None,''):missing.append(f'Line {index} quantity')
                if not isinstance(item,dict) or item.get('unit_price') in (None,''):missing.append(f'Line {index} unit price')
        return missing

    def prepare_invoice(self,data):
        if not isinstance(data,dict):raise ValueError('Invoice details must be an object')
        return {'ready':not self.missing_invoice_fields(data),'missing_fields':self.missing_invoice_fields(data),
            'draft':data,'message':'Complete the listed fields before Jarvis creates and saves the invoice PDF.'}

    def prepare_invoice_from_text(self,text):
        if not isinstance(text,str) or len(text)>4000:raise ValueError('Invoice request must be 1–4000 characters')
        match=re.search(r'\binvoice\s+for\s+(.+?)\s+for\s+(₹|INR\b|USD\b|EUR\b|GBP\b|\$|€|£)?\s*([\d,]+(?:\.\d{1,2})?)\s+for\s+(.+?)[.!?]*$',text,re.I)
        seller={k:os.environ.get('JARVIS_INVOICE_SELLER_'+k.upper(),'').strip() for k in ('name','address','email')}
        if match:
            customer,marker,amount,description=match.groups();currency={'₹':'INR','INR':'INR','$':'USD','USD':'USD','€':'EUR','EUR':'EUR','£':'GBP','GBP':'GBP',None:'INR'}[marker.upper() if marker and marker.isalpha() else marker]
            draft={'seller':seller,'customer':{'name':customer.strip(),'address':'','email':''},'currency':currency,
                'items':[{'description':description.strip(),'quantity':'1','unit_price':amount.replace(',',''),'tax_rate':''}],
                'source_ids':[]}
        else:draft={'seller':seller,'customer':{'name':'','address':'','email':''},'currency':'INR','items':[],'source_ids':[]}
        return self.prepare_invoice(draft)

    def _pdf(self,kind,title,content,invoice=None,sources=()):
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER,TA_LEFT,TA_RIGHT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
        except ImportError:
            raise ValueError('PDF generation needs ReportLab. Install the locked project requirements.') from None
        from io import BytesIO
        try:
            font_path=next((path for path in (r'C:\Windows\Fonts\arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf') if os.path.isfile(path)),None)
            if font_path:
                if 'JarvisSans' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('JarvisSans',font_path))
                font='JarvisSans'
            else:font='Helvetica'
        except Exception:font='Helvetica'
        stream=BytesIO();doc=SimpleDocTemplate(stream,pagesize=A4,rightMargin=19*mm,leftMargin=19*mm,topMargin=18*mm,bottomMargin=18*mm,
            title=title[:180],author='Jarvis local document generator')
        styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='JarvisTitle',parent=styles['Title'],fontName=font,fontSize=21,leading=26,textColor=colors.HexColor('#153b35'),alignment=TA_LEFT,spaceAfter=12))
        styles.add(ParagraphStyle(name='JarvisBody',parent=styles['BodyText'],fontName=font,fontSize=9.5,leading=14,spaceAfter=6,wordWrap='CJK'))
        styles.add(ParagraphStyle(name='JarvisSmall',parent=styles['BodyText'],fontName=font,fontSize=8,leading=11,textColor=colors.HexColor('#53635f')))
        styles.add(ParagraphStyle(name='JarvisRight',parent=styles['JarvisBody'],alignment=TA_RIGHT))
        story=[Paragraph(escape(title),styles['JarvisTitle'])]
        if invoice:
            story.extend([Paragraph('<b>INVOICE</b>',styles['Heading2']),
                Paragraph('Invoice number: '+escape(invoice['invoice_number'])+'<br/>Date: '+escape(invoice['invoice_date'])+
                    (('<br/>Due: '+escape(invoice['due_date'])) if invoice.get('due_date') else ''),styles['JarvisBody'])])
            parties=[[Paragraph('<b>FROM</b><br/>'+escape(invoice['seller']['name'])+'<br/>'+escape(invoice['seller']['address'])+
                (('<br/>'+escape(invoice['seller'].get('email',''))) if invoice['seller'].get('email') else ''),styles['JarvisBody']),
                Paragraph('<b>BILL TO</b><br/>'+escape(invoice['customer']['name'])+'<br/>'+escape(invoice['customer']['address'])+
                (('<br/>'+escape(invoice['customer'].get('email',''))) if invoice['customer'].get('email') else ''),styles['JarvisBody'])]]
            story.append(Table(parties,colWidths=[82*mm,82*mm],style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eef5f1')),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#b8cbc1')),('INNERGRID',(0,0),(-1,-1),.5,colors.white),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),4)])))
            story.append(Spacer(1,9*mm))
            rows=[[Paragraph('<b>Description</b>',styles['JarvisBody']),Paragraph('<b>Qty</b>',styles['JarvisRight']),Paragraph('<b>Unit price</b>',styles['JarvisRight']),Paragraph('<b>Amount</b>',styles['JarvisRight'])]]
            for item in invoice['items']:
                rows.append([Paragraph(escape(item['description']),styles['JarvisBody']),
                    Paragraph(escape(str(item['quantity'])),styles['JarvisRight']),
                    Paragraph(escape(invoice['currency']+' '+item['unit_price']),styles['JarvisRight']),
                    Paragraph(escape(invoice['currency']+' '+item['line_total']),styles['JarvisRight'])])
            table=Table(rows,colWidths=[86*mm,18*mm,32*mm,32*mm],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#173d35')),('TEXTCOLOR',(0,0),(-1,0),colors.white),
                ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#c9d5cf')),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
            story.extend([table,Spacer(1,5*mm)])
            totals=[[Paragraph('Subtotal',styles['JarvisRight']),Paragraph(invoice['currency']+' '+invoice['subtotal'],styles['JarvisRight'])]]
            if invoice['tax_total']!='0.00':totals.append([Paragraph('Tax (as specified)',styles['JarvisRight']),Paragraph(invoice['currency']+' '+invoice['tax_total'],styles['JarvisRight'])])
            totals.append([Paragraph('<b>Total</b>',styles['JarvisRight']),Paragraph('<b>'+escape(invoice['currency']+' '+invoice['total'])+'</b>',styles['JarvisRight'])])
            story.append(Table(totals,colWidths=[118*mm,50*mm],hAlign='RIGHT',style=TableStyle([('ALIGN',(0,0),(-1,-1),'RIGHT'),('LINEABOVE',(0,-1),(-1,-1),.8,colors.HexColor('#173d35')),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)])))
            story.append(Spacer(1,8*mm));story.append(Paragraph('Tax is shown only when supplied in the invoice details. No payment or legal terms were inferred.',styles['JarvisSmall']))
        else:
            for block in content.split('\n\n'):
                story.append(Paragraph(escape(block).replace('\n','<br/>') or '&nbsp;',styles['JarvisBody']))
        if sources:
            story.extend([Spacer(1,7*mm),Paragraph('Source notes',styles['Heading3'])])
            for source in sources:story.append(Paragraph(escape(source['relative_path']+' — '+source['title']),styles['JarvisSmall']))
        def footer(canvas,document):
            canvas.saveState();canvas.setFont(font,8);canvas.setFillColor(colors.HexColor('#60736d'))
            canvas.drawString(19*mm,10*mm,'Generated locally by Jarvis · '+datetime.now(timezone.utc).date().isoformat())
            canvas.drawRightString(A4[0]-19*mm,10*mm,'Page '+str(document.page));canvas.restoreState()
        doc.build(story,onFirstPage=footer,onLaterPages=footer)
        return stream.getvalue()

    def create_invoice(self,data):
        if not isinstance(data,dict):raise ValueError('Invoice details must be an object')
        missing=self.missing_invoice_fields(data)
        if missing:raise ValueError('Invoice needs: '+', '.join(missing))
        seller=self._party(data['seller'],'Your business');customer=self._party(data['customer'],'Customer')
        currency=str(data.get('currency','INR')).strip().upper()
        if not re.fullmatch(r'[A-Z]{3}',currency):raise ValueError('Currency must be a three-letter ISO code')
        items=data['items']
        if len(items)>30:raise ValueError('An invoice can have at most 30 line items')
        normalized=[];subtotal=Decimal('0.00');tax_total=Decimal('0.00')
        for item in items:
            if not isinstance(item,dict):raise ValueError('Each invoice line must be an object')
            desc=str(item.get('description','')).strip()
            if not 1<=len(desc)<=500:raise ValueError('Line item descriptions must contain 1–500 characters')
            qty=_decimal(item.get('quantity'),'Quantity',Decimal('0.0001'),Decimal('100000'))
            unit=_decimal(item.get('unit_price'),'Unit price')
            if unit!=unit.quantize(_CENT):raise ValueError('Unit prices must use at most two decimal places')
            tax_rate=_decimal(item.get('tax_rate') or 0,'Tax rate',Decimal('0'),Decimal('100'))
            line=(qty*unit).quantize(_CENT,rounding=ROUND_HALF_UP);tax=(line*tax_rate/100).quantize(_CENT,rounding=ROUND_HALF_UP)
            subtotal+=line;tax_total+=tax
            normalized.append({'description':desc,'quantity':format(qty.normalize(),'f'),'unit_price':format(unit.quantize(_CENT),'f'),
                'tax_rate':format(tax_rate.normalize(),'f'),'line_total':format(line,'f')})
        invoice_date=self._date(data.get('invoice_date'),date.today().isoformat(),'Invoice date')
        due_date=self._date(data.get('due_date'),None,'Due date') if data.get('due_date') else None
        if due_date and due_date<invoice_date:raise ValueError('Due date cannot be before invoice date')
        invoice_number=str(data.get('invoice_number') or self._next_invoice_number(invoice_date)).strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,39}',invoice_number):raise ValueError('Invoice number must use 1–40 letters, numbers, dots, slashes or dashes')
        total=(subtotal+tax_total).quantize(_CENT,rounding=ROUND_HALF_UP)
        invoice={'invoice_number':invoice_number,'invoice_date':invoice_date.isoformat(),'due_date':due_date.isoformat() if due_date else '',
            'seller':seller,'customer':customer,'currency':currency,'items':normalized,'subtotal':format(subtotal,'f'),
            'tax_total':format(tax_total,'f'),'total':format(total,'f')}
        source_ids=self._source_ids(data.get('source_ids',[]));sources=[self.database.document(i) for i in source_ids]
        title=f"Invoice {invoice_number} · {customer['name']}"
        content=f"Invoice {invoice_number} for {customer['name']}; total {currency} {format(total,'f')}"
        return self._create('invoice',title,content,source_ids,invoice,invoice_number)

    @staticmethod
    def _party(data,label):
        if not isinstance(data,dict):raise ValueError(label+' details are required')
        name=str(data.get('name','')).strip();address=str(data.get('address','')).strip();email=str(data.get('email','')).strip()
        if not 1<=len(name)<=200 or not 1<=len(address)<=1000:raise ValueError(label+' name and address are required')
        if len(email)>320 or any(c in email for c in '\r\n'):raise ValueError(label+' email is invalid')
        return {'name':name,'address':address,'email':email}

    @staticmethod
    def _date(value,default,label):
        try:return date.fromisoformat(str(value or default))
        except (TypeError,ValueError):raise ValueError(label+' must use YYYY-MM-DD') from None

    def _next_invoice_number(self,invoice_date):
        with self.database.connect() as db:n=db.execute("SELECT COUNT(*) FROM generated_documents WHERE kind='invoice'").fetchone()[0]
        # Count is only a convenience for readability; the random artifact ID and
        # unique DB constraint prevent overwrites if concurrent requests race.
        return f"INV-{invoice_date.isoformat().replace('-','')}-{n+1:04d}"

    def create_document(self,kind,title,content,source_ids=None):
        if kind not in ('report','summary','letter'):raise ValueError('Document type must be report, summary or letter')
        if not isinstance(title,str) or not 1<=len(title.strip())<=200:raise ValueError('Document title must contain 1–200 characters')
        if not isinstance(content,str) or not content.strip() or len(content)>100000:raise ValueError('Document content must contain 1–100000 characters')
        ids=self._source_ids(source_ids or []);sources=[self.database.document(i) for i in ids]
        return self._create(kind,title.strip(),'\n\n'.join(content.strip().splitlines()),ids,None,None,sources)

    def _create(self,kind,title,content,source_ids,invoice,invoice_number,sources=()):
        if invoice and not sources:sources=[self.database.document(i) for i in source_ids]
        pdf=self._pdf(kind,title,content,invoice,sources);now=self.clock().timestamp();document_id='doc_'+uuid.uuid4().hex
        safe_name=re.sub(r'[^A-Za-z0-9._-]+','_',invoice_number or title).strip('._-')[:60] or kind
        filename=f'{safe_name}_{document_id[-8:]}.pdf';self.generated_dir.mkdir(parents=True,exist_ok=True)
        path=(self.generated_dir/filename).resolve()
        if not path.is_relative_to(self.generated_dir):raise ValueError('Generated document path is invalid')
        created=False
        try:
            with path.open('xb') as handle:handle.write(pdf);created=True
            digest=hashlib.sha256(pdf).hexdigest()
            with self.database.connect() as db:
                db.execute('''INSERT INTO generated_documents(id,kind,title,filename,relative_path,sha256,mime_type,created_at,
                    invoice_number,source_ids,data_json,summary) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (document_id,kind,title[:200],filename,filename,digest,'application/pdf',now,invoice_number,
                     json.dumps(source_ids),json.dumps(invoice,ensure_ascii=False) if invoice else '{}',content[:1000]))
            return {**self._card(document_id),'created':True}
        except Exception:
            if created:
                try:path.unlink()
                except OSError:pass
            raise

    def _card(self,document_id):
        with self.database.connect() as db:row=db.execute('SELECT * FROM generated_documents WHERE id=?',(document_id,)).fetchone()
        if not row:raise ValueError('Generated document was not found')
        item=dict(row);item['source_ids']=json.loads(item.pop('source_ids'));item['invoice']=json.loads(item.pop('data_json'))
        item['share_approved']=bool(item['share_approved']);item['pinned']=bool(item['pinned'])
        item['preview_url']='/api/documents/file?id='+item['id']
        return item

    def list_documents(self,limit=30):
        with self.database.connect() as db:rows=db.execute("SELECT id FROM generated_documents WHERE status='active' ORDER BY pinned DESC,created_at DESC LIMIT ?",(max(1,min(int(limit),50)),)).fetchall()
        return {'items':[self._card(row['id']) for row in rows]}

    def action(self,document_id,action,confirmation=None):
        if not isinstance(document_id,str) or not re.fullmatch(r'doc_[a-f0-9]{32}',document_id):raise ValueError('Document ID is invalid')
        if action not in ('pin','unpin','dismiss','save','approve_share','revoke_share'):raise ValueError('Unsupported document action')
        if action=='approve_share' and confirmation!='APPROVE SHARE '+document_id:raise ValueError('Exact share approval phrase is required')
        with self.database.connect() as db:
            row=db.execute('SELECT id FROM generated_documents WHERE id=? AND status=\'active\'',(document_id,)).fetchone()
            if not row:raise ValueError('Generated document was not found')
            if action=='pin':db.execute('UPDATE generated_documents SET pinned=1 WHERE id=?',(document_id,))
            elif action=='unpin':db.execute('UPDATE generated_documents SET pinned=0 WHERE id=?',(document_id,))
            elif action=='dismiss':db.execute("UPDATE generated_documents SET status='dismissed' WHERE id=?",(document_id,))
            elif action=='approve_share':db.execute('UPDATE generated_documents SET share_approved=1 WHERE id=?',(document_id,))
            elif action=='revoke_share':db.execute('UPDATE generated_documents SET share_approved=0 WHERE id=?',(document_id,))
        if action=='dismiss':return {'ok':True,'action':action,'id':document_id}
        if action=='save':return {**self._card(document_id),'saved_locally':True}
        return {**self._card(document_id),'ok':True,'action':action}

    def read_file(self,document_id,require_share_approval=False):
        item=self._card(document_id)
        if item['status']!='active':raise ValueError('Generated document was dismissed')
        if require_share_approval and not item['share_approved']:raise ValueError('Document sharing is not approved locally')
        path=(self.generated_dir/item['relative_path']).resolve()
        if not path.is_relative_to(self.generated_dir):raise ValueError('Generated document path is invalid')
        if not path.is_file():raise ValueError('Generated document file is unavailable')
        content=path.read_bytes()
        if len(content)>10_000_000 or not hmac.compare_digest(hashlib.sha256(content).hexdigest(),item['sha256']):
            raise ValueError('Generated document integrity check failed')
        return {'id':item['id'],'filename':item['filename'],'content':content,'share_approved':item['share_approved']}

    def telegram_artifact(self,reference,include_content=False):
        if reference=='latest':
            with self.database.connect() as db:row=db.execute("SELECT id FROM generated_documents WHERE status='active' AND share_approved=1 ORDER BY created_at DESC LIMIT 1").fetchone()
            if not row:return None
            reference=row['id']
        try:item=self.read_file(reference,require_share_approval=True)
        except ValueError:return None
        if not include_content:item.pop('content')
        return item
