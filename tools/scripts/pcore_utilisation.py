#!/usr/bin/env python-nf

###########################################################################
#
#  NETFPGA10G www.netfpga.org
#
#  Module:
#       pcore_utilisation.py
#
#  Description:
#       Parses all XST synthesis report files (synthesis/*.srp) for
#       LUT/FF/etc count, and dumps a table for each pcore, largest-first.
#
#       Very hackish code: Will bail (deliberately) if it comes across some
#       output it doesn't recognise.  You may need to add to the LABELS table
#       below.
#
#       Run in a project directory after synthesis.  Takes no arguments.  eg:
#
#               pcore_utilisation.py |less -S
#
#

from __future__ import with_statement

import glob
import os
import re
import sys

SRP_SUFFIX = '*_wrapper_xst.srp'

SUBSECT = { 'Selected Device'                   : 'device',
            'Slice Logic Utilization'           : 'logic',
            'Slice Logic Distribution'          : 'dist',
            'IO Utilization'                    : 'io',
            'Specific Feature Utilization'      : 'specific',
            'WARNING'                           : 'warning',
            }


LABELS  = { # Slice Logic Utilization
            'Number of Slice Registers'         : 'FFs',
            'Number of Slice LUTs'              : 'LUTs',
            'Number used as Logic'              : 'LUTs_as_logic',
            'Number used as Memory'             : 'LUTs_as_mem',
            'Number used as RAM'                : 'LUTs_as_RAM',
            'Number used as SRL'                : 'LUTs_as_SRL',
            # Slice Logic Distribution
            'Number of LUT Flip Flop pairs used': 'FF_LUT_pairs',
            'Number with an unused Flip Flop'   : 'unused_FF',
            'Number with an unused LUT'         : 'unused_LUT',
            'Number of fully used LUT-FF pairs' : 'fully_used',
            'Number of unique control sets'     : 'control_sets',
            # IO Utilization
            'Number of IOs'                     : 'IOs',
            'Number of bonded IOBs'             : 'bonded_IOs',
            # Specific Feature Utilization
            'Number of BUFG/BUFGCTRLs'          : 'BUFGs',
            'Number of PLL_ADVs'                : 'PLLs',
            'Number of Block RAM/FIFO'          : 'BRAM_FIFOs',
            'Number using Block RAM only'       : 'BRAMs',
            'Number using FIFO only'            : 'FIFOs',
            'Number of GTX_DUALs'               : 'GTXs',
            }


def parse_srp( filename ):
    """
    Parses an XST SRP (Synthesis Report) for utilisation data.
    """
    subsect = None
    data    = {}

    with open( filename ) as f:
        # Skip to beginning of utilisation summary
        for line in f:
            if line.startswith( 'Device utilization summary:' ):
                break
        f.next()

        # Extract data
        for line in f:
            # Terminate at end of section
            if line[0] == '-':
                break
            # Skip empty lines
            line = line.rstrip()
            if not line:
                continue

            # Extract subsection headings
            if not line[0].isspace():
                try:
                    subsect = line[:line.index(':')].strip()
                except ValueError:
                    subsect = line

                try:
                    subsect = SUBSECT[ subsect ]
                except KeyError:
                    print '%s: unknown subsection: %s' % (prog_name, line)
                    sys.exit(1)
                continue

            # Extract subsection data
            elts = line.split(':')
            try:
                label = LABELS[ elts[0].strip() ]
            except KeyError:
                print '%s: unknown data label: %s' % (prog_name, elts[0].strip())
                sys.exit(1)

            # Data component (ie, elts[1]) of the form '156  out of  93120     0%'
            elts = filter( lambda x: x.isdigit(), elts[1].split() )
            elts.append( 0 ) # account for lines that don't have "out of"...
            data.setdefault(subsect, {})[label] = elts[0], int(elts[1])
    return data


def dump_stats( utilisation ):
    """
    Dumps utilisation data.
    """
    def val( subsect, what ):
        return data.get( subsect, {} ).get( what, ('0', 0) )

    # Section headings
    all = [ (1000000, 'pcore', 'LUTs', 'FFs', 'BUFGs', 'PLLs', 'BRAMs', 'GTXs' ), ]
    maxima = [0] * (len(all[0]))

    # Collect desired data
    for pcore, data in utilisation.iteritems():
        try:
            size = int(data['logic']['FFs'][0]) + int(data['logic']['LUTs'][0])
        except KeyError:
            size = 0

        luts, _luts   = val( 'logic'   , 'LUTs' )
        ffs , _ffs    = val( 'logic'   , 'FFs' )
        bufgs, _bufgs = val( 'specific', 'BUFGs' )
        plls, _plls   = val( 'specific', 'PLLs' )
        brams, _brams = val( 'specific', 'BRAM_FIFOs' )
        gts, _gts     = val( 'specific', 'GTXs' )
        all.append( (size, pcore, luts, ffs, bufgs, plls, brams, gts) )

        if _luts  > maxima[2]: maxima[2] = _luts
        if _ffs   > maxima[3]: maxima[3] = _ffs
        if _bufgs > maxima[4]: maxima[4] = _bufgs
        if _plls  > maxima[5]: maxima[5] = _plls
        if _brams > maxima[6]: maxima[6] = _brams
        if _gts   > maxima[7]: maxima[7] = _gts

    # Worst offender first
    all.sort( reverse = True )

    # Calculate column widths
    widths = [0]*len(all[0])
    for elts in all:
        for i in range( 1, len(elts) ):
            if len(elts[i]) > widths[i]:
                widths[i] = len(elts[i])

    # Print table
    fmt = '%%-%ds'*(len(widths)-1) % tuple([x+4 for x in widths[1:]])
    for elts in all:
        print fmt % tuple(elts[1:])
        if elts[2].isdigit():
            print fmt % (('',) + tuple(['%2.1f%%' % (float(x)/m*100) for x, m in zip(elts[2:], maxima[2:])]))
        print
    print fmt % (('Maxima:',) + tuple(['%d' % m for m in maxima[2:]]))


def main( argv ):
    if not os.path.exists( 'system.mhs' ):
        print "%s: system.mhs doesn't exist.  Is this a project directory?" % prog_name
        sys.exit(1)

    utilisation = {}
    for srp in glob.glob( os.path.join( 'synthesis', SRP_SUFFIX ) ):
        pcore = os.path.basename(srp[:-len(SRP_SUFFIX)+1])
        utilisation[pcore] = parse_srp( srp )

    dump_stats( utilisation )


prog_name = os.path.basename( sys.argv[0] )
if __name__ == '__main__':
    main( sys.argv[1:] )
