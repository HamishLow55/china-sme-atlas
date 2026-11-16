"""Public statistics layer: parsing, exact rebuild and integrity regressions. Synthetic rows are test-only."""
import shutil
import tempfile
import unittest
from pathlib import Path
from atlas.core import ROOT, ValidationError
from atlas.statistics import build_china_customs, check_statistics, parse_customs_export, read_csv

ZH='"数据年月","商品编码","商品名称","第一数量","第一计量单位","第二数量","第二计量单位","美元",\n"202501","84862041","合成","1","台","100","千克","1,234,567",\n'
EN=('"Date of data","Commodity code","Commodity","Trading partner code","Trading partner","Locations of importers and exporters code",'
    '"Locations of importers and exporters","Quantity","Unit","Supplementary Quantity","Supplementary Unit","Renminbi Yuan",\n'
    '"202501","84862041","Synthetic","309","Netherlands","31","Shanghai","2","Number of item","50","Kilogram","9,000",\n')

class StatisticsTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def raw(self,name,text):
        p=self.root/'statistics/china_customs/raw'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode('gb18030'));return p
    def test_committed_statistics_reproduce_and_pass_checks(self):
        result=check_statistics(ROOT)
        self.assertEqual(result['comtrade_totals_matched'],['2021','2022','2023','2024','2025'])
        self.assertEqual(result['comtrade_848640_matched'],['2021','2022','2023','2024','2025'])
        self.assertEqual(result['comtrade_903082_matched'],['2021','2022','2023','2024','2025'])
    def test_parser_reads_both_interfaces_and_strips_separators(self):
        meta,rows=parse_customs_export(self.raw('M_2025_01-01_monthly_hs8.csv',ZH))
        self.assertEqual((meta['currency'],meta['interface'],meta['group_by'],rows[0]['value']),('usd','zh','hs8','1234567'))
        meta,rows=parse_customs_export(self.raw('M_2025_01-01_monthly_hs8_partner_province.csv',EN))
        self.assertEqual((meta['currency'],meta['interface'],meta['group_by'],rows[0]['partner_code']),('cny','en','hs8+partner+province','309'))
    def test_parser_rejects_units_names_and_periods_outside_contract(self):
        with self.assertRaisesRegex(ValidationError,'unexpected units'):parse_customs_export(self.raw('M_2025_01-01_monthly_hs8.csv',ZH.replace('"台"','"套"')))
        with self.assertRaisesRegex(ValidationError,'must be named'):parse_customs_export(self.raw('数据导出.csv',ZH))
        with self.assertRaisesRegex(ValidationError,'outside query'):parse_customs_export(self.raw('M_2025_02-12_monthly_hs8.csv',ZH))
    def test_currencies_merge_but_disagreeing_overlaps_are_refused(self):
        self.raw('M_2025_01-01_monthly_hs8.csv',ZH);self.raw('M_2025_01-01_monthly_hs8_cny.csv',ZH.replace('"美元"','"人民币"').replace('1,234,567','8,888,888'))
        build_china_customs(self.root)
        row=read_csv(self.root/'statistics/china_customs/imports_hs8_monthly.csv')[0]
        self.assertEqual((row['usd'],row['cny']),('1234567','8888888'))
        self.raw('M_2025_01-12_monthly_hs8.csv',ZH.replace('1,234,567','1,234,568'))
        with self.assertRaisesRegex(ValidationError,'overlapping pulls disagree'):build_china_customs(self.root)
    def test_tampered_table_or_unlisted_raw_file_is_detected(self):
        shutil.copytree(ROOT/'statistics',self.root/'statistics')
        p=self.root/'statistics/china_customs/imports_hs8_monthly.csv';p.write_text(p.read_text().replace(',125129678,',',125129679,',1))
        with self.assertRaisesRegex(ValidationError,'does not reproduce'):check_statistics(self.root)
        shutil.copy(ROOT/'statistics/china_customs/imports_hs8_monthly.csv',p)
        self.raw('M_2019_01-01_monthly_hs8.csv',ZH.replace('202501','201901'))
        with self.assertRaisesRegex(ValidationError,'does not list exactly'):check_statistics(self.root)

if __name__=='__main__':unittest.main()
