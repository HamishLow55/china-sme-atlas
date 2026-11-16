import copy, hashlib, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
from atlas.pagecheck import preflight,native_rows
from atlas.core import ValidationError
class PageCheckTests(unittest.TestCase):
 def test_worded_percentage_point_change_checks_printed_magnitude_only(self):
  row={'candidate_id':'a','source_id':'s','physical_page':1,'native_value':'减少 2.25 个百分点','native_unit':'percentage_points'}
  self.assertEqual(native_rows([row])[0]['evidence']['reported_value'],'2.25')
  row['native_unit']='percent'
  with self.assertRaises(ValidationError):native_rows([row])
 def test_native_explicit_source_default_cannot_override_packet_or_row(self):
  row={'candidate_id':'a','physical_page':1,'native_value':'7'}
  self.assertEqual(native_rows([row],source_id='s')[0]['source_id'],'s')
  with self.assertRaises(ValidationError):native_rows({'source_id':'other','rows':[row]},source_id='s')
  with self.assertRaises(ValidationError):native_rows([dict(row,source_id='other')],source_id='s')
 def test_native_percent_suffix_requires_unit_and_preserves_percent_scale(self):
  row={'candidate_id':'a','source_id':'s','physical_page':1,'native_value':'0.84%','native_unit':'percent'}
  self.assertEqual(native_rows([row])[0]['evidence']['reported_value'],'0.84')
  row['native_unit']='CNY'
  with self.assertRaises(ValidationError):native_rows([row])
 def test_native_excerpt_agreement_does_not_pass_wrong_original_page(self):
  packet={'source':{'source_id':'s','local_path':'ignored.pdf'},'rows':[{'candidate_id':'native-a','physical_page':2,'native_value':'1,234.50','excerpt':'The supplied excerpt says 1,234.50'}]}
  before=copy.deepcopy(packet);rows=native_rows(packet)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'original.pdf';p.write_bytes(b'original')
   data={'sources':{'s':{'locator_kind':'pdf','sha256':hashlib.sha256(b'original').hexdigest(),'page_count':2}}}
   got=preflight(rows,data,{'s':p},extractor=lambda _: {'status':'ok','pages':['1,234.50','other page 7']})
   self.assertEqual(got[0]['reason'],'native_token_absent')
  self.assertEqual(packet,before)
 def test_native_source_conflicts_and_duplicate_ids_fail(self):
  row={'candidate_id':'a','source_id':'s','physical_page':1,'native_value':'7'}
  with self.assertRaises(ValidationError):native_rows([row,row])
  with self.assertRaises(ValidationError):native_rows({'source_id':'other','rows':[row]})
  with self.assertRaises(ValidationError):native_rows({'source_id':'s','source':{'source_id':'other'},'rows':[row]})
 def test_native_qualitative_and_malformed_numbers_are_not_silently_skipped(self):
  for value in ['several tools','1,23','NaN','1e3',1.25,True]:
   with self.subTest(value=value),self.assertRaises(ValidationError):
    native_rows([{'candidate_id':'a','source_id':'s','physical_page':1,'native_value':value}])
  with self.assertRaises(ValidationError):native_rows([])
 def test_native_ranges_retain_upper_bound_and_signed_scale(self):
  row={'candidate_id':'a','source_id':'s','physical_page':1,'native_value':'(1,234.50)','relation':'range'}
  with self.assertRaises(ValidationError):native_rows([row])
  row['native_upper_value']='2,000.00'
  ev=native_rows([row])[0]['evidence']
  self.assertEqual(ev,{'page':1,'reported_value':'-1234.50','reported_upper_value':'2000.00'})
 def test_native_locator_and_identity_cannot_be_inferred(self):
  row={'candidate_id':'a','source_id':'s','physical_page':1,'native_value':7}
  for field in ['candidate_id','source_id','physical_page','native_value']:
   bad=dict(row);bad.pop(field)
   with self.subTest(field=field),self.assertRaises(ValidationError):native_rows([bad])
  row['physical_page']=True
  with self.assertRaises(ValidationError):native_rows([row])
 def test_hash_pdf_kind_and_read_failure_do_not_pass(self):
  row={'observation_id':'a','source_id':'s','evidence':{'page':1,'reported_value':'7'}}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.pdf';p.write_bytes(b'x');sha=hashlib.sha256(b'x').hexdigest()
   record={'locator_kind':'pdf','sha256':sha,'page_count':1};data={'sources':{'s':record}}
   record['sha256']='z'*64
   self.assertEqual(preflight([row],data,{'s':p})[0]['reason'],'invalid_registered_hash')
   record['sha256']='0'*64
   self.assertEqual(preflight([row],data,{'s':p})[0]['reason'],'hash_mismatch')
   record['sha256']=sha;record['locator_kind']='html'
   self.assertEqual(preflight([row],data,{'s':p})[0]['reason'],'registered_source_not_pdf')
   record['locator_kind']='pdf'
   with patch('atlas.pagecheck.digest',side_effect=PermissionError):
    self.assertEqual(preflight([row],data,{'s':p})[0]['reason'],'local_read_failed')
 def test_extraction_failure_and_invalid_page_are_diagnostics(self):
  row={'observation_id':'a','source_id':'s','evidence':{'page':999,'reported_value':'7'}}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.pdf';p.write_bytes(b'x');data={'sources':{'s':{'locator_kind':'pdf','sha256':hashlib.sha256(b'x').hexdigest(),'page_count':1}}}
   def fail(_):raise OSError('unavailable')
   self.assertEqual(preflight([row],data,{'s':p},extractor=fail)[0]['reason'],'extraction_failed')
   self.assertEqual(preflight([row],data,{'s':p},extractor=lambda _: {'status':'ok','pages':['7']})[0]['reason'],'page_out_of_extracted_range')
 def test_native_page_and_range_tokens(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.pdf';p.write_bytes(b'x');sha=hashlib.sha256(b'x').hexdigest();rows=[{'observation_id':'a','source_id':'s','evidence':{'page':2,'reported_value':'-12.3','reported_upper_value':'5'}}];data={'sources':{'s':{'locator_kind':'pdf','sha256':sha,'page_count':2}}}
   self.assertEqual(preflight(rows,data,{'s':p},extractor=lambda _: {'status':'ok','pages':['one','loss (12.3) and 5'],'error':''})[0]['status'],'pass')
 def test_metadata_claim_and_cache(self):
  row={'observation_id':'a','source_id':'s','evidence':{'page':1,'reported_value':'7'}}
  self.assertEqual(preflight([row],{'sources':{}},{})[0]['reason'],'unknown_source')
  self.assertEqual(preflight([row],{'sources':{'s':{'locator_kind':'pdf','sha256':'x','page_count':1}}},{})[0]['reason'],'invalid_registered_hash')
  self.assertEqual(preflight([row],{'sources':{'s':{'locator_kind':'pdf','sha256':'0'*64,'page_count':0}}},{})[0]['reason'],'invalid_registered_page_count')
  self.assertEqual(preflight([row],{'sources':{'s':{'locator_kind':'pdf','sha256':'0'*64,'page_count':1}}},{'s':'/tmp/Semis notes/x.pdf'})[0]['reason'],'protected_path')
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.pdf';p.write_bytes(b'x');sha=hashlib.sha256(b'x').hexdigest();data={'sources':{'s':{'locator_kind':'pdf','sha256':sha,'page_count':2}}}
   self.assertEqual(preflight([row],data,{'s':p},extractor=lambda _: {'status':'ok','pages':['none','7'],'error':''})[0]['reason'],'native_token_absent')
   row['evidence']['reported_upper_value']='8';self.assertEqual(preflight([row],data,{'s':p},extractor=lambda _: {'status':'ok','pages':['7','7'],'error':''})[0]['reason'],'native_token_absent')
   calls=[]; rows=[dict(row,observation_id=str(i)) for i in range(2)]; rows[0]['evidence']={'page':1,'reported_value':'7'};rows[1]['evidence']={'page':1,'reported_value':'7'}
   got=preflight(rows,data,{'s':p},extractor=lambda _: (calls.append(1) or {'status':'ok','pages':['7'],'error':''}));self.assertTrue(all(x['reason']=='registered_page_count_mismatch' for x in got));self.assertEqual(len(calls),1)

class WrappedCellFragmentTests(unittest.TestCase):
 """A filing may wrap a number inside a narrow table cell, so no extraction mode returns it
 contiguously. The evidence declares the on-page fragments and the check confirms them."""
 WRAPPED=['专用设备     1,400,740,2                      增加 3.25',
          '             840,484,445. 40.00    47.80      40.21',
          '制造行业           38.08                      个百分点']
 def _run(self,evidence,pages=None):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'original.pdf';p.write_bytes(b'original')
   data={'sources':{'s':{'locator_kind':'pdf','sha256':hashlib.sha256(b'original').hexdigest(),'page_count':1}}}
   rows=[{'observation_id':'a','source_id':'s','evidence':evidence}]
   return preflight(rows,data,{'s':p},extractor=lambda _:{'status':'ok','pages':['\n'.join(pages or self.WRAPPED)]})[0]
 def test_declared_fragments_confirm_a_value_split_inside_a_cell(self):
  got=self._run({'page':1,'reported_value':'1400740238.08','page_wrapped_fragments':['1,400,740,2','38.08']})
  self.assertEqual(got['status'],'pass')
  self.assertEqual(got['reason'],'page_wrapped_fragments_confirmed')
 def test_the_same_value_without_a_declaration_still_reports_absence(self):
  got=self._run({'page':1,'reported_value':'1400740238.08'})
  self.assertEqual(got['status'],'mismatch')
  self.assertEqual(got['reason'],'native_token_absent')
 def test_fragments_that_do_not_reassemble_into_the_reported_value_are_refused(self):
  for fragments in (['1,400,740,2','38.09'],['1,400,740,9','38.08'],['1,400,740,2'],['38.08','1,400,740,2']):
   with self.subTest(fragments=fragments):
    got=self._run({'page':1,'reported_value':'1400740238.08','page_wrapped_fragments':fragments})
    self.assertEqual(got['status'],'mismatch')
 def test_fragments_absent_from_the_page_are_refused(self):
  got=self._run({'page':1,'reported_value':'1400740238.08','page_wrapped_fragments':['1,400,740,2','38.08']},
                pages=['a page that prints no such figure'])
  self.assertEqual(got['status'],'mismatch')
 def test_fragments_must_appear_in_the_declared_order(self):
  # 38.08 precedes 1,400,740,2 on this page, so the reassembly is not what the page shows.
  got=self._run({'page':1,'reported_value':'1400740238.08','page_wrapped_fragments':['1,400,740,2','38.08']},
                pages=['38.08 comes first','then 1,400,740,2 later'])
  self.assertEqual(got['status'],'mismatch')

class ScannedPageTests(unittest.TestCase):
 """A scanned filing has no text layer, so no token can be found on its pages. The check must say
 it could not reach the page rather than report the value as absent, which would read as evidence
 against a row that a human verified against the rendered image."""
 def _run(self,pages,page=1):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'scan.pdf';p.write_bytes(b'scan')
   data={'sources':{'s':{'locator_kind':'pdf','sha256':hashlib.sha256(b'scan').hexdigest(),'page_count':len(pages)}}}
   rows=[{'observation_id':'o','source_id':'s','evidence':{'page':page,'reported_value':'1110539705.21'}}]
   return preflight(rows,data,{'s':p},extractor=lambda _: {'status':'ok','pages':pages})[0]
 def test_empty_page_reports_missing_text_layer_not_a_missing_value(self):
  got=self._run(['',''])
  self.assertEqual(got['status'],'unavailable')
  self.assertEqual(got['reason'],'page_has_no_text_layer')
  self.assertNotIn('missing_native_values',got)
 def test_whitespace_only_page_counts_as_no_text_layer(self):
  self.assertEqual(self._run(['   \n\t  ','x'])['reason'],'page_has_no_text_layer')
 def test_a_page_with_text_but_without_the_value_still_mismatches(self):
  got=self._run(['营业收入 25,948,187,501.48','other'])
  self.assertEqual(got['status'],'mismatch')
  self.assertEqual(got['reason'],'native_token_absent')
 def test_a_text_page_in_an_otherwise_scanned_document_is_still_checked(self):
  got=self._run(['','1,110,539,705.21'],page=2)
  self.assertEqual(got['status'],'pass')

class CompoundScaledPartTests(unittest.TestCase):
 """Japanese filings print an amount as a compound of scaled pieces with the unit words between the
 digits -- 4,428億24百万円 is 442,824 million yen -- so no flat extraction returns the value as one
 token. The parts are declared, each is confirmed literally and in order, and the validator requires
 them to sum to exactly the value the row records."""
 PAGE='  出荷額                        4,428億24百万円 (前期比       10.3％増)'
 def _run(self,parts,value='442824'):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'jp.pdf';p.write_bytes(b'jp')
   data={'sources':{'s':{'locator_kind':'pdf','sha256':hashlib.sha256(b'jp').hexdigest(),'page_count':1}}}
   ev={'page':1,'reported_value':value}
   if parts is not None:ev['page_compound_scaled_parts']=parts
   rows=[{'observation_id':'o','source_id':'s','evidence':ev}]
   return preflight(rows,data,{'s':p},extractor=lambda _: {'status':'ok','pages':[self.PAGE]})[0]
 def test_declared_parts_confirm_a_compound_the_page_never_prints_whole(self):
  got=self._run([{'value':'4,428','unit':'JPY_100m'},{'value':'24','unit':'JPY_million'}])
  self.assertEqual(got['status'],'pass')
  self.assertEqual(got['reason'],'page_compound_scaled_parts_confirmed')
 def test_without_the_declaration_the_value_still_reports_absent(self):
  self.assertEqual(self._run(None)['reason'],'native_token_absent')
 def test_a_part_absent_from_the_page_is_refused(self):
  got=self._run([{'value':'4,428','unit':'JPY_100m'},{'value':'77','unit':'JPY_million'}])
  self.assertEqual(got['status'],'mismatch')
 def test_parts_must_appear_in_the_declared_order(self):
  got=self._run([{'value':'24','unit':'JPY_million'},{'value':'4,428','unit':'JPY_100m'}])
  self.assertEqual(got['status'],'mismatch')

class CompoundPartArithmeticTests(unittest.TestCase):
 def test_parts_must_sum_to_the_reported_value(self):
  from atlas.evidence import compound_parts_total
  from atlas.core import require
  units={'JPY_100m':{'base_unit':'JPY','scale':'100000000'},'JPY_million':{'base_unit':'JPY','scale':'1000000'}}
  total,base=compound_parts_total([{'value':'4,428','unit':'JPY_100m'},{'value':'24','unit':'JPY_million'}],units,require,'o')
  self.assertEqual(base,'JPY')
  self.assertEqual(total,442824*1000000)
 def test_parts_mixing_base_units_are_refused(self):
  from atlas.evidence import compound_parts_total
  from atlas.core import require
  units={'JPY_100m':{'base_unit':'JPY','scale':'100000000'},'USD_million':{'base_unit':'USD','scale':'1000000'}}
  with self.assertRaises(ValidationError):
   compound_parts_total([{'value':'1','unit':'JPY_100m'},{'value':'2','unit':'USD_million'}],units,require,'o')
