#!/usr/bin/env python
#-*- coding: utf-8 -*-

import sys
import os
import argparse
import glob
from datetime import datetime
import logging
import re

import pdftotext


__author__ = 'Andrew Wurster'
__license__ = 'GPL'
__version__ = '1.0.0'
__email__ = 'dev@awurster.com'
__status__ = 'dev'


_RE_PAID_ON_DATE = re.compile('Paid on Date\s+(?P<paid_on_date>\d\d\/\d\d\/\d\d)')
_RE_DONATION = re.compile('DA DONATION CHARITABLE\s+\$\s+(?P<donation>[\d\,\.]{1,})')
_RE_TAXABLE_GROSS_EARNINGS = re.compile(
    'TAXABLE GROSS EARNINGS\s+\$\s+(?P<taxable_gross_earnings>[\d\,\.]{1,})'
    )
_RE_TOTAL_TAX_DEDUCTED = re.compile('TOTAL TAX DEDUCTED\s+\$\s+(?P<total_tax_deducted>[\d\,\.]{1,})')
_RE_TOTAL_NET_PAY = re.compile('TOTAL NET PAY.+\$\s+(?P<total_net_pay>[\d\,\.]{1,})')
_RE_SUPERANNUATION = re.compile(
    'SS Superannuation\s+(?P<percentage>\d+\.\d+)\%\s+\$\s+(?P<superannuation>[\d\,\.]{1,})'
    )

_FIELDNAMES = [
    'paid_on_date',
    'donation',
    'taxable_gross_earnings',
    'total_tax_deducted',
    'total_net_pay',
    'superannuation'
]

# Configure root level logger
logger = logging.getLogger(__name__)
ch = logging.StreamHandler()
logger.addHandler(ch)

def write_results_to_file(payslips, outfile, format):
    """
    Given a list of JSON LDAP search results, writes them to a file.

    :param payslips: List of dictionaries containing payslip data
    :param outfile: Destination
    :param format: choose CSV or JSON output, defaults to CSV
    :return: None
    """

    valid_slips = [p['results'] for p in payslips if p['status'] == 'valid']
    logger.info('Found %s valid payslip objects from %s total files scanned.' % (len(valid_slips), len(payslips)))

    of = None
    if outfile:
        of = open(outfile, 'w')
    else:
        of = sys.stdout
        sys.stdout.write('\n')

    logger.info('Writing %s formatted results to %s\n' % (format, of.name))
    if format == 'csv':
        import csv
        if valid_slips:
            writer = csv.DictWriter(
                of,
                quoting=csv.QUOTE_ALL,
                fieldnames=_FIELDNAMES
            )
            writer.writeheader()
            rows = sorted(valid_slips,
                key=lambda d: datetime.strptime(d['paid_on_date'], '%d/%m/%y')
                )
            writer.writerows(rows)
        else:
            logger.error('No valid payslips found')
            sys.exit(1)

    elif format == 'json':
        import json
        for l in valid_slips:
            of.write(f'{json.dumps(l)}\n')
    else:
        logger.warn('Unrecognised format %s.' % format)
        logger.debug('Dumping raw results for all payslips: %s' % payslips)
        sys.exit(1)

def get_pdf_files(input_dir, pattern):
    """
    Get a list of PDF files for parsing.
    :param input_dir: Directory to scan for input files
    :param pattern: Glob pattern to match for valid PDF files
    :return pdfs: List of valid PDF files to be parsed
    """
    pdfs = []
    for pdf in glob.glob(os.path.join(input_dir, pattern)):
        logger.debug('Found glob match: %s' % pdf)
        pdfs.append(pdf)

    if pdfs:
        logger.info('Found %s glob matches for PDFs to scan' % len(pdfs))
        return pdfs
    else:
        logger.error('Found no PDF glob matches for %s in %s' %
            (pattern, input_dir))
        sys.exit(1)

def parse_payslip(pdf):
    """
    Parse PDF lines from pdftotext and return dictionary of payslip data.
    :param pdf: PDF object to parse.
    :return results: payslip data
    """
    # sigh...

    payslip = {}
    payslip['data'] = []
    for page in pdf:
        payslip['data'].extend(page.split('\n'))

    # print(payslip)
    results = {}
    for line in payslip['data']:
        paid_on_date = _RE_PAID_ON_DATE.search(line)
        donation = _RE_DONATION.search(line)
        taxable_gross_earnings = _RE_TAXABLE_GROSS_EARNINGS.search(line)
        total_tax_deducted = _RE_TOTAL_TAX_DEDUCTED.search(line)
        total_net_pay = _RE_TOTAL_NET_PAY.search(line)
        superannuation = _RE_SUPERANNUATION.search(line)

        if paid_on_date:
            results['paid_on_date'] = paid_on_date.group('paid_on_date')
        if donation:
            results['donation'] = donation.group('donation')
        if taxable_gross_earnings:
            results['taxable_gross_earnings'] = taxable_gross_earnings.group('taxable_gross_earnings')
        if total_tax_deducted:
            results['total_tax_deducted'] = total_tax_deducted.group('total_tax_deducted')
        if total_net_pay:
            results['total_net_pay'] = total_net_pay.group('total_net_pay')
        if superannuation:
            results['superannuation'] = superannuation.group('superannuation')

    payslip['results'] = results

    if all (k in results for k in _FIELDNAMES):
        payslip['status'] = 'valid'
        logger.debug('Valid payslip data found: %s' % payslip)
    else:
        payslip['status'] = 'invalid'
        logger.debug('Payslip fields missing from data: %s' % payslip)

    return payslip

def get_payslips_from_pdfs(pdfs):
    """
    Convert list of PDFs to text and scan them for payslip data.
    :param pdfs: List of valid PDF files to be parsed
    :param glob_pattern: Glob pattern to match for valid PDF files
    :return payslips: List of dictionaries of valid payslip data
    """
    payslips = []
    for pdf in pdfs:
        payslip = {}
        payslip['file'] = pdf
        with open(pdf,'rb') as pf:
            try:
                p = pdftotext.PDF(pf)
            except Exception as e:
                logger.debug('Exception scanning PDF document: %s' % str(e))
                payslip['data'] = []
                payslip['status'] = 'failed'
        if p:
            payslip = parse_payslip(p)
        payslips.append(payslip)

    return payslips

def main(args):
    """
    The entrypoint for the Python script.
    :param args: Program arguments provided to the Python script
    :return: None
    """

    logger.debug('Invoked program with arguments: %s' % str(args))

    pdfs = get_pdf_files(args.input_dir, args.pattern)

    payslips = get_payslips_from_pdfs(pdfs)

    write_results_to_file(
        payslips,
        args.output_file,
        args.format.lower()
        )

    sys.exit()


def parse_args():
    """
    Parses the program arguments.

    :return: An 'args' class containing the program arguments as attributes.
    """

    parser = argparse.ArgumentParser(
        description='Convert PDFs of payslips into parsable CSV output.')

    # The directory containing input PDFs.
    parser.add_argument('-i',
                        '--input-dir',
                        required=False,
                        default=os.getcwd(),
                        help='Location of PDF files containing payslip data (defaults to current directory.')

    # The input file pattern.
    parser.add_argument('-p',
                        '--pattern',
                        required=False,
                        default='*.pdf',
                        help='The input file names to match where payslip data resides (defaults to *.pdf).')

    # The output file to write results to, defaults to stdout.
    parser.add_argument('-o',
                        '--output-file',
                        required=False,
                        default=None,
                        help='The filename where output data will be written (defaults to stdout).')

    # Output formatting
    parser.add_argument('-f',
                        '--format',
                        required=False,
                        default='csv',
                        help='(csv|json) The output format for results (defaults to csv).')

    # Whether to print debug logging statements
    parser.add_argument('-v',
                        '--verbose',
                        required=False,
                        action='store_true',
                        help='Display verbose debugging output.')


    args = parser.parse_args()

    # If verbose mode is on, show DEBUG level logs and higher.
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('Verbose logging enabled.')
    else:
        logger.setLevel(logging.INFO)

    return args


"""---- Entry point ----"""
if __name__ == '__main__':

    args = parse_args()
    main(args)
