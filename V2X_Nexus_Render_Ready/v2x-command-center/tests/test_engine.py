"""Dependency-free sanity checks for the research prototype."""
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import normalize_config, run_experiment


class ExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=run_experiment({'seed':42,'duration':32,'vehicles':20,'load':.75,'capacity':6})

    def test_matching_packet_demand(self):
        fifo,ai=(self.result['results'][key]['metrics'] for key in ('fifo','ai'))
        self.assertEqual(fifo['generated'],ai['generated'])
        self.assertEqual(fifo['safety_generated'],ai['safety_generated'])

    def test_valid_pdr_and_awareness(self):
        for name in ('fifo','ai'):
            m=self.result['results'][name]['metrics']
            for field in ('pdr_pct','safety_pdr_pct','awareness_pct','blindspot_reduction_pct'):
                self.assertGreaterEqual(m[field],0)
                self.assertLessEqual(m[field],100)
            self.assertEqual(m['generated'],m['sent']+m['expired']+m['pending'])
            self.assertEqual(m['sent'],m['delivered']+m['lost'])

    def test_reproducible(self):
        again=run_experiment({'seed':42,'duration':32,'vehicles':20,'load':.75,'capacity':6})
        for name in ('fifo','ai'):
            self.assertEqual(self.result['results'][name]['metrics'],again['results'][name]['metrics'])

    def test_frames_shape(self):
        for method in ('fifo','ai'):
            self.assertEqual(len(self.result['results'][method]['snapshots']),32)
            self.assertEqual(len(self.result['results'][method]['series']['tick']),32)

    def test_bounded_settings(self):
        c=normalize_config({'capacity':10000,'vehicles':-3,'seed':'bad','load':'nan','source':'nope'})
        self.assertEqual(c['capacity'],24)
        self.assertEqual(c['vehicles'],8)
        self.assertEqual(c['seed'],42)
        self.assertEqual(c['load'],.52)
        self.assertEqual(c['source'],'synthetic')


if __name__ == '__main__':unittest.main()
