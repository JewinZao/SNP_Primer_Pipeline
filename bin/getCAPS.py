#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  getcaps
#
#  Copyright 2016 Junli Zhang <zhjl86@gmail.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#

# getcaps3.py use files with names starting with "flanking*" from step 5 of the pipeline
# getcaps3.py now uses all the variation sites that can differ all homeologs

# change the input wildcard and the paths of primer3 and muscle accordingly.
# NOTES: the output primer pair includes the common primer and the primer with SNP A or T, you need to change the 3' nucleartide to get the primer for the other SNP.

### Imported
from subprocess import call
import getopt, sys, os, re
from glob import glob
#########################

blast = sys.argv[1] # 0 or 1, whether to blast
# get all the raw sequences
raw = glob("flanking_temp_marker*") # All file names start from "flanking"
raw.sort()

iupac = {"R": "AG", "Y": "TC", "S": "GC", "W": "AT", "K": "TG", "M": "AC"}

#from sys import platform
def get_software_path(base_path):
	if sys.platform.startswith('linux'): # linux
		primer3_path = base_path + "/primer3_core"
		muscle_path = base_path + "/muscle"
	elif sys.platform == "win32" or sys.platform == "cygwin": # Windows...
		primer3_path = base_path + "/primer3_core.exe"
		muscle_path = base_path + "/muscle.exe"
	elif sys.platform == "darwin": # MacOSX
		primer3_path = base_path + "/primer3_core_darwin64"
		muscle_path = base_path + "/muscle3.8.31_i86darwin64"
	return primer3_path, muscle_path

# function to get reverse complement
def ReverseComplement(seq):
	# too lazy to construct the dictionary manually, use a dict comprehension
	seq1 = 'ATCGTAGCatcgtagc'
	seq_dict = { seq1[i]:seq1[i+4] for i in range(16) if i < 4 or 8<=i<12 }
	return "".join([seq_dict[base] for base in reversed(seq)])

# simple Tm calculator
def Tm(seq):
	t=0
	for a in seq:
		if a=='A' or a=='T':
			t=t+2
		if a=='C' or a=='G':
			t=t+4
	return t

# calculate GC content of a sequence
def Calc_GC(seq):
	t = 0.0 # float
	for a in seq:
		if a=='C' or a=='G':
			t += 1
	return t / len(seq) * 100

# function to find the segments with largest Tm
def FindLongestSubstring(s1, s2):
	longestStart = 0
	longestEnd = 0
	largestTm = 0
	start = 0
	gaps = [i for i, c in enumerate(s1) if c=='-' or s2[i]=='-']
	gaps.append(len(s1))
	for gap in gaps:
		end = gap
		tm = Tm(s1[start:end])
		if  tm > largestTm:
			longestStart = start
			longestEnd = end
			largestTm = tm
		start = gap + 1
	nL = len(s1[:longestStart].replace("-","")) # number of bases on the left of the longest segments
	nR = len(s1[longestEnd:].replace("-",""))  # number of bases on the right of the longest segments
	return [longestStart, longestEnd, nL, nR]

# get the list of sequences in the homeolog groups for comparison with current primer
def get_homeo_seq(fasta, target, ids, align_left, align_right):
	s1 = fasta[target] # primer sequence in the template with gaps
	seq2comp = [] # final sequence to compare for each other homeolog
	for k in ids:
		s2 = fasta[k]
		targetSeq = s1[align_left:(align_right + 1)]
		homeoSeq = s2[align_left:(align_right + 1)]
		#print "Targetseq ", targetSeq
		#print "homeoSeq  ", homeoSeq
		# Get the sequences for comparison
		indexL, indexR, nL, nR = FindLongestSubstring(targetSeq, homeoSeq)
		indexL += align_left
		indexR += align_left
		seqL = s2[:indexL].replace("-","")
		seqR = s2[indexR:].replace("-","")
		#print "indexL, indexR, nL, nR ", indexL, indexR, nL, nR
		#print "s2[indexL:indexR] ", s2[indexL:indexR]
		if len(seqL) < nL: # in case it does not have enough bases
			seqL = "-" * (nL - len(seqL)) + seqL
		if len(seqR) < nR:
			seqL = seqR + "-" * (nR - len(seqR))
		seqk = seqL[::-1][:nL][::-1] + s2[indexL:indexR] + seqR[:nR]
		seq2comp.append(seqk)
		#print k, "\t", seqk
	return seq2comp

# step 1: read the enzyme file
RE_file = "/home/junli/Documents/Git/getcaps_pipeline/striderc.403.parsed"
# function to parse the enzyme file and return a dictionary with enzyme name and sequences
class Restriction_Enzyme(object):
	def __init__(self, name, seq):
		self.name = name
		self.seq = seq.lower()
		self.length = len(seq)
		self.template_seq = ""
		self.primer_end_pos = None
		self.caps = "No"
		self.dcaps = "No"
		self.allpos = [] # all the match positions in the template
		self.change_pos = None

	# classes
class Primers(object):
	"""A primer set designed by Primer3"""
	def __init__(self):
		self.name = ""
		self.start = 0
		self.end = 0
		self.length = 0
		self.tm = 0.0
		self.gc = 0.0
		self.anys = 0.0
		self.three = 0.0
		self.hairpin = 0.0
		self.end_stability = 0.0
		self.seq = ""
		self.difthreeall = "NO" # whether 3' site can differ all
	def formatprimer(self):
		formatout = "\t".join(str(x) for x in [self.start, self.end, self.length, self.tm, self.gc, self.anys, self.three, self.end_stability, self.hairpin, self.seq, ReverseComplement(self.seq), self.difthreeall])
		return(formatout)

class PrimerPair(object):
	"""A pair of primers designed by Primer3"""
	def __init__(self):
		self.left = Primers()
		self.right = Primers()
		self.compl_any = "NA"
		self.compl_end = "NA"
		self.penalty = "NA"
		self.product_size = 0


def parse_RE_file(RE_file):
	REs = {}
	with open(RE_file) as file_one:
		for line in file_one:
			enzyme, seq = line.rstrip().split("\t")
			REs[enzyme] = Restriction_Enzyme(enzyme, seq)
	return REs

# step 2: function to test whether a SNP can be converted to an enzyme cutting site
def string_dif(s1, s2): # two strings with equal length
	return [i for i in xrange(len(s1)) if s1[i] != s2[i]]


def find_substring(substring, string): # find all the starting index of a substring
	return [m.start() for m in re.finditer(substring, string)]


def test_enzyme(enzyme, wild_seq, mut_seq): # enzyme is an Restriction_Enzyme object
	enzyme_seq = enzyme.seq
	enzyme_name = enzyme.name
	wild_seq = wild_seq.lower()
	mut_seq = mut_seq.lower()
	wild_allpos = find_substring(enzyme_seq, wild_seq)
	mut_allpos = find_substring(enzyme_seq, mut_seq)
	#print "enzyme is: ", enzyme_name
	#print "wild_allpos: ", wild_allpos
	#print " mut_allpos: ", mut_allpos
	enzyme.allpos = wild_allpos
	if len(wild_allpos) != len(mut_allpos): # snp cause digestion differenc
		enzyme.caps = "Yes"
		enzyme.template_seq = wild_seq
		#return enzyme
	# else no caps found, check dcaps
	snp_pos = string_dif(wild_seq, mut_seq)[0] # snp position in the template
	#print "wild flanking:   ", wild_seq[snp_pos -6:snp_pos + 7]
	#print "mutant flanking: ", mut_seq[snp_pos -6:snp_pos + 7]
	snp_A = wild_seq[snp_pos]
	snp_B = mut_seq[snp_pos]
	#print "snp_pos is", snp_pos
	for i in range(len(enzyme_seq)):
		ss = enzyme_seq[0:i] + "[atgc]" + enzyme_seq[i+1:] # regular expression
		# try wild_seq first
		for m in re.finditer(ss, wild_seq):
			#print m.start(), m.end(), m.span(), m.group()
			if snp_pos in range(m.start(), m.end()):
				print "Find RE across the SNP and it is ", enzyme.name, m.group()
				change_pos = m.start() + i # which was changed
				if abs(snp_pos - change_pos) > 1: # to insure the introduced mutaton is at least 2 bases far from the snp
					print "One nt can be changed to fit enzyme", enzyme.name
					enzyme.dcaps = "Yes"
					enzyme.template_seq = wild_seq[:change_pos] + enzyme_seq[i].upper() + wild_seq[change_pos+1:]
					enzyme.change_pos = change_pos
					if change_pos < snp_pos:
						enzyme.primer_end_pos = range(change_pos + 1, snp_pos) # a list of primer end positions
					else:
						enzyme.primer_end_pos = range(snp_pos + 1, change_pos) # a list of primer end positions
					print "change position and primer end postions are ", change_pos, enzyme.primer_end_pos
					print "wild_allpos ", wild_allpos
					break
		# break the loop if dcaps found
		if enzyme.dcaps == "Yes":
			break
		for m in re.finditer(ss, mut_seq):
			#print m.start(), m.end(), m.span(), m.group()
			if snp_pos in range(m.start(), m.end()):
				print "Find RE across the SNP and it is ", enzyme.name, m.group()
				change_pos = m.start() + i # which was changed
				if abs(snp_pos - change_pos) > 1: # to insure the introduced mutaton is at least 2 bases far from the snp
					print "One nt can be changed to fit enzyme", enzyme.name
					enzyme.dcaps = "Yes"
					enzyme.template_seq = mut_seq[:change_pos] + enzyme_seq[i].upper() + mut_seq[change_pos+1:]
					enzyme.change_pos = change_pos
					if change_pos < snp_pos:
						enzyme.primer_end_pos = range(change_pos + 1, snp_pos) # a list of primer end positions
					else:
						enzyme.primer_end_pos = range(snp_pos + 1, change_pos) # a list of primer end positions
					print "change position and primer end postions are ", change_pos, enzyme.primer_end_pos
					print "wild_allpos ", wild_allpos
					break
	return enzyme
			
# function to count mismtaches
def mismatchn (s1, s2):
	return sum(c1!=c2 for c1,c2 in zip(s1,s2))

# function to blast and parse the output of each primer in the wheat genome
# depends on function: mismtachn
def primer_blast(primer_for_blast, outfile_blast):
	forblast = open("for_blast.fa", 'w') # for blast against the gnome
	for k, v in primer_for_blast.items(): # k is the sequence and v is the number
		forblast.write(">" + v + "\n" + k + "\n")
	forblast.close()
	blast_hit = {} # matched chromosomes for primers: less than 2 mismatches in the first 4 bps from 3'
	### for blast
	reference = "/Library/WebServer/Documents/blast/db/nucleotide/161010_Chinese_Spring_v1.0_pseudomolecules.fasta"
	cmd2 = 'blastn -task blastn -db ' + reference + ' -query for_blast.fa -outfmt "6 std qseq sseq qlen slen" -num_threads 3 -word_size 7 -out ' + outfile_blast
	print "Step 2: Blast command:\n", cmd2
	call(cmd2, shell=True)
	# process blast file
	# blast fields
	# IWB50236_7A_R	IWGSC_CSS_7DS_scaff_3919748	98.718	78	1	0	24	101	4891	4968	1.55e-30	138	CTCATCAAATGATTCAAAAATATCGATRCTTGGCTGGTGTATCGTGCAGACGACAGTTCGTCCGGTATCAACAGCATT	CTCATCAAATGATTCAAAAATATCGATGCTTGGCTGGTGTATCGTGCAGACGACAGTTCGTCCGGTATCAACAGCATT	101 5924
	# Fields: 
	# 1: query id, subject id, % identity, alignment length, mismatches, gap opens, 
	# 7: q. start, q. end, s. start, s. end, evalue, bit score
	# 13: q. sequence, s. sequence, q. length s. length
	for line in open(outfile_blast):
		if line.startswith('#'):
			continue
		fields = line.split("\t")
		query, subject, pct_identity, align_length= fields[:4]
		qstart, qstop, sstart, sstop = [int(x) for x in fields[6:10]]
		qseq, sseq = fields[12:14]
		qlen = int(fields[14])
		n1 = qlen - qstop
		if n1 < 2 and mismatchn(qseq[(n1 - 4):], sseq[(n1 - 4):]) + n1 < 2: # if less than 2 mismtaches in the first 4 bases from the 3' end of the primer
			blast_hit[query] = blast_hit.setdefault(query, "") + ";" + subject + ":" + str(sstart)
	return blast_hit

# parse the flanking sequence input

def caps(seqfile):
	#flanking_temp_marker_IWB1855_7A_R_251.fa
	snpname, chrom, allele, pos =re.split("_|\.", seqfile)[3:7]
	print "snpname, chrom, allele, pos ", snpname, chrom, allele, pos
	getcaps_path = os.path.dirname(os.path.realpath(__file__))
	directory = "CAPS_output"
	if not os.path.exists(directory):
		os.makedirs(directory)
	out = directory + "/selected_CAPS_primers_" + snpname + ".txt"
	target = "2AS" # target sequence name
	product_min = 50
	product_max = 250
	alt_allele = iupac[allele][0] # choose A or T
	
	# software path
	primer3_path, muscle_path = get_software_path(getcaps_path)
	#muscle_path = "muscle"
	#primer3_path = "primer3_core"

	########################
	# STEP 0: create alignment file and primer3output file
	RawAlignFile = "alignment_raw_" + snpname + ".fa"
	alignmentcmd = muscle_path + " -in " + seqfile + " -out " + RawAlignFile + " -quiet"
	print "Alignment command: ", alignmentcmd
	call(alignmentcmd, shell=True)
	
	# Primer3 input and output
	#outfile = open(out, 'w') # output file
	snp_pos = int(pos) - 1 # 0-based
	########################
	# read alignment file
	fasta = {} # dictionary for alignment

	with open(RawAlignFile) as file_one:
		for line in file_one:
			if line.startswith(">"):
				sequence_name = line.rstrip().lstrip(">")
			else:
				fasta.setdefault(sequence_name, "")
				fasta[sequence_name] += line.rstrip()

	# get the variaiton site among sequences
	ids = [] # all other sequence names
	for kk in fasta.keys():
		key_chr = kk.split("_")[2] # sequence chromosome name
		if chrom in key_chr or key_chr in chrom: # 3B contig names do not have chromosome arm
			target = kk
		else:
			ids.append(kk)
			
	print "The target: ", target
	print "The other groups: ", ids

	alignlen = len(fasta[target])
	print "Alignment length: ", alignlen
	
	# get the target ID template base coordinate in the alignment
	t2a = {} # template to alignment
	a2t = {}
	ngap = 0 # gaps
	for i in range(alignlen):
		if fasta[target][i] == "-":
			ngap += 1
			continue
		t2a[i - ngap] = i
		a2t[i] = i - ngap

	print "last key of t2a", i - ngap
	print "last key of a2t", i
	
	seq_template = fasta[target].replace("-","") # remove all gaps

	variation = [] # variation sites that can differ ALL
	variation2 = [] # variation sites that can differ at least 2 homeologs
	
	# calculate gap number on the left and right
	gap_left_target = len(fasta[target]) - len(fasta[target].lstrip('-'))
	gap_left = max([len(v) - len(v.lstrip('-')) for k, v in fasta.items()])
	gap_right = min([len(v.rstrip('-')) for k, v in fasta.items()])
	print "gap_left_target, gap_left and gap_right: ", gap_left_target, gap_left, gap_right
	
	diffarray = {} # a list of 0 or 1: the same as or different from the site in each sequences of ids
	#for i in range(alignlen):
	for i in range(gap_left, gap_right): # exclude 20 bases on each side
		b1 = fasta[target][i]
		if b1 == "-":  # target non-gap base
			ngap += 1
			continue
		pos_template = a2t[i] # position in the target template (no gaps)
		if pos_template < 20 or pos_template > len(seq_template) - 20:
			continue
		nd = 0 # number of difference
		da = [0] * len(ids) # differ array
		m = 0 # counter of next loop
		if pos_template < snp_pos:
			align_left = t2a[pos_template - 19] # 20 bp left of current position
			align_right = i
		else:
			align_left = i # 20 bp left of current position
			align_right = t2a[pos_template + 19]
		seq2comp = get_homeo_seq(fasta, target, ids, align_left, align_right) # list of sequences for comparison
		for k in seq2comp:
			if pos_template < snp_pos:
				b2 = k[-1] # homeolog non-gap bas
			else:
				b2 = k[0]
			if b1 != b2:
				nd += 1
				da[m] = 1 # m sequence has variation from target
			m += 1

		# for each site pos_template
		diffarray[pos_template] = da
		if nd == len(ids): # different from all other sequences
			if pos_template not in variation: # in case multiple gaps
				variation.append(pos_template)
		if nd > 0: # different from at least 1 other sequence
			if pos_template not in variation2: # in case multiple gaps
				variation2.append(pos_template)
	
	print "Sites that can differ all\n", variation
	print "\nSites that can differ at least 1\n", variation2
	#print "\nKeys of diffarray: ", diffarray.keys()
	
	############################################################
	################ Get CAPS information ######################
	# step 1: read the enzyme file
	RE_file = getcaps_path + "/striderc.403.parsed_JZ.txt" # this one removed some duplicated cuttings
	REs = parse_RE_file(RE_file) # get the list of restriction enzymes
	# step 2: get the list of enzymes that can be used for caps or dcaps
	SNP_A, SNP_B = iupac[allele] # SNP 2 alleles
	print "SNP_A, SNP_B ", SNP_A, SNP_B
	wild_seq = seq_template[:snp_pos] + SNP_A + seq_template[snp_pos+1:]
	mut_seq = seq_template[:snp_pos] + SNP_B + seq_template[snp_pos+1:]
	caps_list = []
	dcaps_list = []
	for k in REs:
		enzyme = test_enzyme(REs[k], wild_seq, mut_seq)
		if enzyme.caps == "Yes":
			caps_list.append(enzyme)
		elif enzyme.dcaps == "Yes":
			dcaps_list.append(enzyme)
	print "caps_list is ", caps_list
	print "dcaps_list is ", [x.name for x in dcaps_list]
	
	########################################################
	# loop to write primer3 input for each variation site
	# primer3 inputfile
	primer3input = directory + "/primer3.input." + snpname
	p3input = open(primer3input, 'w')

	#seq_template = fasta[target].replace("-","") # remove all gaps

	# because A and T give lower Tm, so use them as template
	if alt_allele in "ATat":
		seq_template = seq_template[:snp_pos] +  alt_allele + seq_template[snp_pos + 1:]
	# for dcaps
	product_min = 220
	product_max = 500
	n = 0 # number to see how many records were written to primer3 input file
	for enzyme in dcaps_list:
		for primer_end_pos in enzyme.primer_end_pos: # a list of potential end positions
			for i in variation:
				if primer_end_pos > snp_pos:
					left_end = i + 1
					right_end = primer_end_pos + 1
				else:
					left_end = primer_end_pos + 1
					right_end = i + 1
				if right_end - left_end < product_min - 35 or right_end - left_end > product_max - 35: # suppose both primers are 18 bp
					continue
				settings = "PRIMER_TASK=generic" + "\n" + \
				"SEQUENCE_ID=" + target + "-dCAPS-" + enzyme.name + "-" + enzyme.seq + "-" + str(i) + "\n" + \
				"SEQUENCE_TEMPLATE=" + enzyme.template_seq + "\n" + \
				"PRIMER_PRODUCT_SIZE_RANGE=" + str(product_min) + "-" + str(product_max) + "\n" + \
				"PRIMER_THERMODYNAMIC_PARAMETERS_PATH=" + getcaps_path + "/primer3_config/"  + "\n" + \
				"PRIMER_MAX_SIZE=25" + "\n" + \
				"PRIMER_PAIR_MAX_DIFF_TM=6.0" + "\n" + \
				"PRIMER_FIRST_BASE_INDEX=1" + "\n" + \
				"PRIMER_LIBERAL_BASE=1" + "\n" + \
				"PRIMER_NUM_RETURN=5"  + "\n" + \
				"PRIMER_EXPLAIN_FLAG=1"  + "\n" + \
				"SEQUENCE_FORCE_LEFT_END=" + str(left_end) + "\n" + \
				"SEQUENCE_FORCE_RIGHT_END=" + str(right_end) + "\n" + \
				"="
				n += 1
				p3input.write(settings + "\n")
	# for caps
	product_min = 300
	product_max = 900
	for enzyme in caps_list:
		for i in variation: # sites that can differ all
			if i < snp_pos:
				left_end = i + 1
				right_end = -1000000
			else:
				left_end = -1000000
				right_end = i + 1
			settings = "PRIMER_TASK=generic" + "\n" + \
			"SEQUENCE_ID=" + target + "-CAPS-" + enzyme.name + "-" + enzyme.seq + "-" + str(i) + "\n" + \
			"SEQUENCE_TEMPLATE=" + enzyme.template_seq + "\n" + \
			"PRIMER_PRODUCT_SIZE_RANGE=" + str(product_min) + "-" + str(product_max) + "\n" + \
			"PRIMER_THERMODYNAMIC_PARAMETERS_PATH=" + getcaps_path + "/primer3_config/"  + "\n" + \
			"PRIMER_MAX_SIZE=25" + "\n" + \
			"PRIMER_PAIR_MAX_DIFF_TM=6.0" + "\n" + \
			"PRIMER_FIRST_BASE_INDEX=1" + "\n" + \
			"PRIMER_LIBERAL_BASE=1" + "\n" + \
			"PRIMER_NUM_RETURN=5"  + "\n" + \
			"PRIMER_EXPLAIN_FLAG=1"  + "\n" + \
			"SEQUENCE_FORCE_LEFT_END=" + str(left_end) + "\n" + \
			"SEQUENCE_FORCE_RIGHT_END=" + str(right_end) + "\n" + \
			"SEQUENCE_TARGET=" + str(snp_pos - 20) + ",40" + "\n" + \
			"="
			n += 1
			p3input.write(settings + "\n")	

	p3input.close()
	
	if n == 0:
		print "No primer3 input were found"
		outfile = open(out, 'w')
		outfile.write("Sites that can differ all in target " + target + "\n")
		outfile.write(", ".join([str(x + 1) for x in variation])) # change to 1 based
		outfile.write("\nCAPS cut information\n") # change to 1 based
		outfile.write("Enzyme\tEnzyme_seq\tChange_pos\tOther_cut_pos\n")
		for enzyme in caps_list:
			outfile.write(enzyme.name + "\t" + enzyme.seq + "\t" + ", ".join([str(x + 1) for x in enzyme.allpos]) + "\n")
		outfile.write("\ndCAPS cut information\n") # change to 1 based
		for enzyme in dcaps_list:
			outfile.write(enzyme.name + "\t" + enzyme.seq + "\t" + str(enzyme.change_pos) + "\t" + ", ".join([str(x + 1) for x in enzyme.allpos]) + "\n")
		outfile.close()
		return 0
	# primer3 output file
	primer3output = directory + "/primer3.output." + snpname
	p3cmd = primer3_path + " -default_version=2 -output=" + primer3output + " " + primer3input
	print "Primer3 command 1st time: ", p3cmd
	call(p3cmd, shell=True)

	##########################
	### parse primer 3 primer check output
	primerpairs = {} # sequence ID is the key

	with open(primer3output) as infile:
		for line in infile:
			line = line.strip()
			if "SEQUENCE_ID" in line:
				seqid = line.split("=")[1]
				primerpairs[seqid] = PrimerPair()
			elif "PRIMER_PAIR_0_PENALTY" in line:
				primerpairs[seqid].penalty = line.split("=")[1]
			elif "PRIMER_PAIR_0_COMPL_ANY" in line:
				primerpairs[seqid].compl_any = line.split("=")[1]
			elif "PRIMER_PAIR_0_COMPL_END" in line:
				primerpairs[seqid].compl_end = line.split("=")[1]
			elif "PRIMER_PAIR_0_PRODUCT_SIZE" in line:
				primerpairs[seqid].product_size = int(line.split("=")[1])
			elif "PRIMER_LEFT_0_SEQUENCE" in line:
				primerpairs[seqid].left.seq = line.split("=")[1]
			elif "PRIMER_LEFT_0=" in line:
				primerpairs[seqid].left.start = int(line.split("=")[1].split(",")[0])
				primerpairs[seqid].left.length = int(line.split("=")[1].split(",")[1])
				primerpairs[seqid].left.end = primerpairs[seqid].left.start + primerpairs[seqid].left.length - 1
			elif "PRIMER_LEFT_0_TM" in line:
				primerpairs[seqid].left.tm = float(line.split("=")[1])
			elif "PRIMER_LEFT_0_GC_PERCENT" in line:
				primerpairs[seqid].left.gc = float(line.split("=")[1])
			elif "PRIMER_LEFT_0_SELF_ANY_TH" in line:
				primerpairs[seqid].left.anys = float(line.split("=")[1])
			elif "PRIMER_LEFT_0_SELF_END_TH" in line:
				primerpairs[seqid].left.three = float(line.split("=")[1])
			elif "PRIMER_LEFT_0_HAIRPIN_TH" in line:
				primerpairs[seqid].left.hairpin = float(line.split("=")[1])
			elif "PRIMER_LEFT_0_END_STABILITY" in line:
				primerpairs[seqid].left.end_stability = float(line.split("=")[1])
			elif "PRIMER_RIGHT_0_SEQUENCE" in line:
				primerpairs[seqid].right.seq = line.split("=")[1]
			elif "PRIMER_RIGHT_0=" in line:
				primerpairs[seqid].right.start = int(line.split("=")[1].split(",")[0])
				primerpairs[seqid].right.length = int(line.split("=")[1].split(",")[1])
				primerpairs[seqid].right.end = primerpairs[seqid].right.start - primerpairs[seqid].right.length + 1
			elif "PRIMER_RIGHT_0_TM" in line:
				primerpairs[seqid].right.tm = float(line.split("=")[1])
			elif "PRIMER_RIGHT_0_GC_PERCENT" in line:
				primerpairs[seqid].right.gc = float(line.split("=")[1])
			elif "PRIMER_RIGHT_0_SELF_ANY_TH" in line:
				primerpairs[seqid].right.anys = float(line.split("=")[1])
			elif "PRIMER_RIGHT_0_SELF_END_TH" in line:
				primerpairs[seqid].right.three = float(line.split("=")[1])
			elif "PRIMER_RIGHT_0_HAIRPIN_TH" in line:
				primerpairs[seqid].right.hairpin = float(line.split("=")[1])
			elif "PRIMER_RIGHT_0_END_STABILITY" in line:
				primerpairs[seqid].right.end_stability = float(line.split("=")[1])


	# write to file
	outfile = open(out, 'w')
	outfile.write("index\tproduct_size\ttype\tstart\tend\tlength\tTm\tGCcontent\tany\t3'\tend_stability\thairpin\tprimer_seq\tReverseComplement\t3'differall\tpenalty\tcompl_any\tcompl_end\tPrimerID\tmatched_chromosomes\n")
	# Get primer list for blast
	primer_for_blast = {}
	final_primers = {}
	nL = 0 # left primer count
	nR = 0 # right primer count
	for i, pp in primerpairs.items():
		if pp.product_size != 0:
			pl = pp.left
			pr = pp.right
			if pl.seq not in primer_for_blast:
				nL += 1
				pl.name = "L" + str(nL)
				primer_for_blast[pl.seq] = pl.name # use seq as keys
			else:
				pl.name = primer_for_blast[pl.seq]
			if pr.seq not in primer_for_blast:
				nR += 1
				pr.name = "R" + str(nR)
				primer_for_blast[pr.seq] = pr.name # because a lot of same sequences
			else:
				pr.name = primer_for_blast[pl.seq]
			pp.left = pl
			pp.right = pr
			final_primers[i] = pp
				
	# blast primers
	blast_hit = {}
	outfile_blast = directory + "/primer_blast_out_" + target + ".txt"
	if blast:
		blast_hit = primer_blast(primer_for_blast, outfile_blast) # chromosome hit for each primer
	# write output file
	for i, pp in final_primers.items():
		varsite = int(i.split("-")[-1]) # variation site
		pl = pp.left
		pr = pp.right
		# check whether 3' can differ all: not necessary for here, because I only used sites that can differ all.
		if varsite in variation:
			pl.difthreeall = "YES"
			pr.difthreeall = "YES"
		outfile.write("\t".join([i, str(pp.product_size), "LEFT", pl.formatprimer(), pp.penalty, pp.compl_any, pp.compl_end, pl.name, blast_hit.setdefault(pl.name, "")]) + "\n")
		outfile.write("\t".join([i, str(pp.product_size), "RIGHT", pr.formatprimer(), pp.penalty, pp.compl_any, pp.compl_end, pr.name, blast_hit.setdefault(pr.name, "")]) + "\n")
	
	outfile.write("\n\nSites that can differ all in target " + target + "\n")
	outfile.write(", ".join([str(x + 1) for x in variation])) # change to 1 based
	# write CAPS cut information
	outfile.write("\n\nCAPS cut information\n") # change to 1 based
	outfile.write("Enzyme\tEnzyme_seq\tChange_pos\tOther_cut_pos\n")
	for enzyme in dcaps_list + caps_list:
		outfile.write(enzyme.name + "\t" + enzyme.seq + "\t" + str(enzyme.change_pos) + "\t" + ", ".join([str(x + 1) for x in enzyme.allpos]) + "\n")
	# close outfile
	outfile.close()

# loop for all snp sequence files

for ff in raw:
	caps(ff)
	