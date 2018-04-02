##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 2018 Steve R <steversig@virginmedia.com>
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, see <http://www.gnu.org/licenses/>.
##

import sigrokdecode as srd

def decode_bit(edges):
    # Datasheet says long pulse is 3 times short pulse.
    lmin = 2 # long min multiplier
    lmax = 5 # long max multiplier
    eqmin = 0.5 # equal min multiplier
    eqmax = 1.5 # equal max multiplier
    if ( # 0 -___-___
        (int(edges[1]) >= int(edges[0]) * lmin and int(edges[1]) <= int(edges[0]) * lmax) and
        (int(edges[2]) >= int(edges[0]) * eqmin and int(edges[2]) <= int(edges[0]) * eqmax) and
        (int(edges[3]) >= int(edges[0]) * lmin and int(edges[3]) <= int(edges[0]) * lmax)):
        return '0'
    elif ( # 1 ---_---_
        (int(edges[0]) >= int(edges[1]) * lmin and int(edges[0]) <= int(edges[1]) * lmax) and
        (int(edges[0]) >= int(edges[2]) * eqmin and int(edges[0]) <= int(edges[2]) * eqmax) and
        (int(edges[0]) >= int(edges[3]) * lmin and int(edges[0]) <= int(edges[3]) * lmax)):
        return '1'
    elif ( # float ---_-___
        (int(edges[1]) >= int(edges[0]) * lmin and int(edges[1]) <= int(edges[0]) * lmax) and
        (int(edges[2]) >= int(edges[0]) * lmin and int(edges[2]) <= int(edges[0]) * lmax) and
        (int(edges[3]) >= int(edges[0]) * eqmin and int(edges[3]) <= int(edges[0]) * eqmax)):
        return 'f'
    else:
        return 'U'

def pinlabels(bit_count):
    if bit_count <= 6:
        return 'A%i' % (bit_count - 1)
    else:
        return 'A%i/D%i' % (bit_count - 1, 12 - bit_count)

def decode_model(model, bits):
    if model == 'maplin_l95ar':
        address = 'Addr' # Address pins A0 to A5
        for i in range(0, 6):
            address = address + ' %i:' % (i + 1) + \
                      ('on' if bits[i][0] == '0' else 'off')
        button = 'Button'
        # Button pins A6/D5 to A11/D0
        if bits[6][0] == '0' and bits[11][0] == '0':
            button = button + ' A ON/OFF'
        elif bits[7][0] == '0' and bits[11][0] == '0':
            button = button + ' B ON/OFF'
        elif bits[9][0] == '0' and bits[11][0] == '0':
            button = button + ' C ON/OFF'
        elif bits[8][0] == '0' and bits[11][0] == '0':
            button = button + ' D ON/OFF'
        else:
            button = button + ' Unknown'
        return ['%s' % address, bits[0][1], bits[5][2], \
                '%s' % button, bits[6][1], bits[11][2]]

class Decoder(srd.Decoder):
    api_version = 3
    id = 'rc_encode'
    name = 'RC encode'
    longname = 'Remote control encoder'
    desc = 'PT2262/HX2262/SC5262 remote control encoder protocol.'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = []
    channels = (
        {'id': 'data', 'name': 'Data', 'desc': 'Data line'},
    )
    annotations = (
        ('bits', 'Bits'),
        ('pins', 'Pins'),
        ('remote', 'Remote'),
    )
    annotation_rows = (
        ('bits', 'Bits', (0,)),
        ('pins', 'Pins', (1,)),
        ('remote', 'Remote', (2,)),
    )
    options = (
        {'id': 'remote', 'desc': 'Remote', 'default': 'none', 
            'values': ('none', 'maplin_l95ar')},
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.samplenumber_last = None
        self.pulses = []
        self.bits = []
        self.labels = []
        self.bit_count = 0
        self.bit_first = None
        self.bit_last = None
        self.state = 'IDLE'

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.model = self.options['remote']

    def decode(self):
        while True:
            pin = self.wait({0: 'e'})
            self.state = 'DECODING'

            if not self.samplenumber_last: # Set counters to start of signal.
                self.samplenumber_last = self.samplenum
                self.bit_first = self.samplenum
                continue

            if self.bit_count < 12: # Decode A0 to A11.
                self.bit_count += 1
                for i in range(0, 4): # Get four pulses for each bit.
                    if i > 0:
                        pin = self.wait({0: 'e'}) # Get next 3 edges.
                    samples = self.samplenum - self.samplenumber_last
                    self.pulses.append(samples) # Save the pulse width.
                    self.samplenumber_last = self.samplenum
                self.bit_last = self.samplenum
                self.bits.append([decode_bit(self.pulses), self.bit_first,
                                  self.bit_last]) # Save states and times.
                self.put(self.bit_first, self.bit_last, self.out_ann,
                         [0, [decode_bit(self.pulses)]]) # Write decoded bit.
                self.put(self.bit_first, self.bit_last, self.out_ann,
                         [1, [pinlabels(self.bit_count)]]) # Write pin labels.
                self.pulses = []
                self.bit_first = self.samplenum
            else:
                if self.model != 'none':
                    self.labels = decode_model(self.model, self.bits)
                    self.put(self.labels[1], self.labels[2], self.out_ann,
                             [2, [self.labels[0]]]) # Write model decode.
                    self.put(self.labels[4], self.labels[5], self.out_ann,
                             [2, [self.labels[3]]]) # Write model decode.
                samples = self.samplenum - self.samplenumber_last
                pin = self.wait({'skip': 8 * samples}) # Wait for end of sync bit.
                self.bit_last = self.samplenum
                self.put(self.bit_first, self.bit_last, self.out_ann,
                         [0, ['Sync']]) # Write sync label.
                self.reset() # Reset and wait for next set of pulses.
                self.state = 'DECODE_TIMEOUT'
            if not self.state == 'DECODE_TIMEOUT':
                self.samplenumber_last = self.samplenum