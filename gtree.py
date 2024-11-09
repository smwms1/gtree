#!/usr/bin/env python3

# GTREE - a simple family tree program.
# Copyright (C) 2024  Solomon Wood

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

import glob
import sys
import os
import platform
import ansi2html
import configparser
import dataclasses
import shlex
import traceback

from typing import Iterable, Callable

# This checks whether the system is a Windows system. If it is, we need to sort
# out the console so that we can display ANSI escape codes. If there if an
# error, the user will be informed and the program will exit immediately.
if platform.system() == "Windows":
	try:
		import colorama # type: ignore
		colorama.just_fix_windows_console()
	except ImportError:
		print("Could not load 'colorama' module. This is required on Windows.")
		print("To install, run")
		print("\tpip install colorama")
		exit(-1)

# This section describes the global variables for the program. PERSONS is the
# complete list of all the persons in the database. COLOR is a configuration
# variable which describes whether color is turned on. It has been abandoned;
# why wouldn't you want color? CLI is a reference to the current instance of
# CommandLineInterface(). LINEBREAKS describes a deprecated feature of whether
# to insert linebreaks between tree entities. ASCII chooses whether to use ASCII
# line drawing characters or the standard Unicode ones. Finally, FILENAME refers
# to the active filename. Ideally, we would move everything into CLI, but this
# might be too much of a reform.
PERSONS			: list					= []
COLOR			: bool					= True	# type: deprecated
CLI										= None
LINEBREAKS		: bool					= False	# type: deprecated
ASCII			: bool					= False
FILENAME		: str					= None

# This section contains some text templates and constants. WELCOMETEXT and
# COPYRIGHT provide the welcome to the program. STANDALONEHTML and HTML provide
# HTML template documents that are used to print reports, after the usage of the
# ansi2html formatter. STANDALONEHTML is used with the :standalone option, while
# HTML is used with the :inline option.

WELCOMETEXT		= """
Welcome to GTREE version 1.30.
"""

COPYRIGHT		= """
GTREE version 1.30, Copyright (C) 2024  Solomon Wood
GTREE comes with ABSOLUTELY NO WARRANTY. This is free
software, and you are welcome to redistribute it under
certain conditions.
"""

STANDALONEHTML			= """
<!DOCTYPE html>
<html>
	<head>
		<title>GTREE: {FamilyTreeName}</title>
		<meta charset="utf-8">
		<style>
			._gtree_private_css_tag_tree, ._gtree_private_css_tag_tree span {
				font-family: 	monospace;
				font-size:		10pt;
				line-height:	1.20;
				white-space:	pre-wrap;
				word-wrap:		break-word;
				padding:		0;
				margin:			0;
			}
			._gtree_private_css_tag_header {
				font-family: 	'Times New Roman', Times, serif;
				font-style:		italic;
			}
		</style>
	</head>
	<body>
		<h3 class="_gtree_private_css_tag_header">{Title}</h3>
		<p>
			<div class="_gtree_private_css_tag_tree">{Data}</div>
		</p>
		<p>Generated by GTREE (<a href="https://wood.eu.com/gtree" class="lnk">https://wood.eu.com/gtree</a>)</p>
	</body>
</html>
"""

HTML	= """
<style>
	._gtree_private_css_tag_tree, ._gtree_private_css_tag_tree span {
		font-family: 	monospace;
		font-size:		10pt;
		line-height:	1.20;
		white-space:	pre-wrap;
		word-wrap:		break-word;
		padding:		0;
		margin:			0;
	}
	._gtree_private_css_tag_header {
		font-family: 	'Times New Roman', Times, serif;
		font-style:		italic;
	}
</style>
<h3 class="_gtree_private_css_tag_header">{Title}</h3>
<p>
	<div class="_gtree_private_css_tag_tree">{Data}</div>
</p>
<p>Generated by GTREE (<a href="https://wood.eu.com/gtree" class="lnk">https://wood.eu.com/gtree</a>)</p>
"""

WELCOME			= WELCOMETEXT.rstrip() + COPYRIGHT

# MARK: Graphics
# The Graphics class provides ANSI escape codes which are used for formatting
# and styling. It provides a Common section, with common codes, such as RESET
# and CLEAR, a Decoration section with codes for decoration (and for resetting)
# decoration, and a Color section, with both Foreground and Background sections
# for each of the eight colors, and a default color. Finally, it is home to the
# LineDrawing logic, which chooses which characters will be used when drawing
# tree charts.

class Graphics:
	class Common:
		_CSI		= "\033["
		RESET		= "\033[0m"
		CLEAR		= "\033[2J\033[H"
		NORMAL		= "\033[0m"
	class Decoration:
		BOLD		= "\033[1m"
		ITALIC		= "\033[3m"
		INVERSE		= "\033[7m"
		RESETBOLD	= "\033[22m"
	class Color:
		class Foreground:
			BLACK		= "\033[30m"
			RED			= "\033[31m"
			GREEN		= "\033[32m"
			YELLOW		= "\033[33m"
			BLUE		= "\033[34m"
			MAGENTA		= "\033[35m"
			CYAN		= "\033[36m"
			WHITE		= "\033[37m"
			DEFAULT		= "\033[39m"
		class Background:
			BLACK		= "\033[40m"
			RED			= "\033[41m"
			GREEN		= "\033[42m"
			YELLOW		= "\033[43m"
			BLUE		= "\033[44m"
			MAGENTA		= "\033[45m"
			CYAN		= "\033[46m"
			WHITE		= "\033[47m"
			DEFAULT		= "\033[49m"
	class LineDrawing:
		def __init__(self, color, ascii=False):
			if not ascii:
				self.ITEMS = {
					"PIPE"	: "│  ",
					"ELBOW"	: "└──",
					"TEE"	: "├──",
					"BLANK"	: "   "
				}
			else:
				self.ITEMS = {
					"PIPE"	: "|  ",
					"ELBOW"	: "`--",
					"TEE"	: "|--",
					"BLANK"	: "   "
				}
			self.color = color
			self.colorise()
		
		def colorise(self):
			for each in self.ITEMS.keys():
				setattr(
					self,
					each,
					(
						self.color
						+ self.ITEMS[each]
						+ "\033[39m"
					)
				)

# The diag() function performs a simple job of printing text to the output,
# ensuring it is indented by the magic value of 19 spaces. There was a reason
# why this number was chosen; I cannot remember it.
def diag(string, end="\n", file=sys.stdout):
	for line in str(string).split("\n"):
		if line.strip() == "":
			file.write(end)
			continue
		file.write((" "*19)+line+end)
	
	file.flush()

# MARK: Utilities
# You shall find here general utilities which are used in various parts of the
# code. Many of them, such as the ones following, are used when constructing
# diagrams and reports, but they tend to provide general functionality that is
# used by more than, or not specific to, one part of the program.

def display_exception(e=None, die=False):
	if e is None:
		e = sys.exception()

	diag(type(e).__name__, str(e))

	tb			= e.__traceback__
	tb_format	= traceback.format_tb(tb)
	tb_format.reverse()

	diag("Traceback" "(stack level, most recent call first):")

	for i, line in enumerate(tb_format):
		diag("%d %s" % (
			i,
			line.strip().split("\n")[0].removeprefix("    ")
		))

	if die:
		exit(666)

def parse_args(args: Iterable[str], optslen=None, postslen=None):
	OPTS	= []
	POSTS	= []

	remainder_is_posts	= False

	for argument in args:
		if remainder_is_posts:
			POSTS.append(argument)

		elif argument == "::":
			remainder_is_posts	= True
			continue
		
		elif argument.startswith(":"):
			argument	= argument.removeprefix(":")

			if ":" in argument:
				argument	= argument.split(":")
				assert len(argument) == 2
			
			OPTS.append(argument)

		else:
			POSTS.append(argument)

	if optslen	is not None:	assert len(OPTS)	== optslen
	if postslen	is not None:	assert len(POSTS)	== postslen

	return OPTS, POSTS

# Adds a bold header to some text.
def add_header(name: str):
	return "%s%s:%s\n" % (
		Graphics.Decoration.BOLD,
		name,
		Graphics.Common.RESET
	)

# Formats an ID value from a person with a style and an 'end' value. This is
# used to combine an ID number with a person's name so that it stands out.
def fmt_id(
		person,
		style	= Graphics.Color.Foreground.MAGENTA,
		end		= Graphics.Common.RESET
	):
	return "%s(%s)%s" % (
		style,
		person.id,
		end
	)

# Returns a 'person string', with a person's name and his ID number. This is
# only used by the profile() method, but it may be used more generally in the
# future.
def add_person(person):
	return "\t%s %s\n" % (
		person.get_name(),
		fmt_id(person)
	)

# Produces a similar Field report, with a key, and a text, and an 'ideal'
# padding for the section.
def add_field(key: str, text: str, align_text=False, embolden=True, ideal=28):
	if text:
		fmt	= "{:>%d}" % (max(28, ideal) - 12)

		return "%s%s%s %s\n" % (
			Graphics.Decoration.BOLD if embolden else "",
			"{:<12}".format(key+":"),
			Graphics.Decoration.RESETBOLD if embolden else "",
			fmt.format(text) if align_text else text
		)
	else:
		return ""
	
# Creates a section with persons using the add_header() and add_person()
# functions.
def section_with_persons(name: str, gives_persons: Callable[..., Iterable]):
	data	= ""
	persons	= gives_persons()
	if persons:
		data	+= add_header(name)
		for person in persons:
			data	+= add_person(person)

	return data

# Returns a completed parser, read from a filename and (if required) a default
# dictionary.
def parser_from_ini(filename: str, defaults={}):
	parser	= configparser.ConfigParser()
	parser.read_dict(defaults)
	parser.optionxform	= lambda x: x
	with open(filename) as file:
		parser.read_file(file)
	
	return parser

# Print an exit message, and then exit with a code.
def do_exit(code: int):
	diag("Goodbye!\n")
	exit(code)

def get_bool(string: str):
	if string == "True":
		return True
	else:
		return False

def resolve_gender(gender: str):
	gender = gender.lower().strip()
	if gender.startswith("m"):		return 1
	elif gender.startswith("f"):	return 2
	else:							return 0

def get_gender(gender: int):
	if gender == 1:	return "Male"
	if gender == 2: return "Female"
	else:			return "Unknown"

def resolve_globs(path: str):
	result = glob.glob(path)
	if len(result) == 0:
		raise FileNotFoundError("Could not find match for file '%s'"%path)
	else:
		return result[0]

def table_format(persons: list):
	FMT = "{:>6} \033[1m\033[32m{:>16}\033[0m {:>20} \033[35m{:>12}\033[0m {:>12} {:>12} {:>12} {:>12}\n"
	output = FMT.format(
		"Title",
		"First Name",
		"Middle Name",
		"Last Name",
		"Birth",
		"Death",
		"Gender",
		"ID"
	)
	for person in persons:
		output += FMT.format(
			person.title,
			person.first_name,
			person.middle_name,
			person.last_name,
			person.birth_date,
			person.death_date,
			get_gender(person.gender),
			person.id
		)
	output = output[0:-1]
	return output

# Return the actual length of a string, ignoring ANSI escapes, non-printable
# characters, and taking into account newlines, and tabs (for example).
def actuallen(string: str):
	length		= 0
	skipping	= False
	for each in string:
		if skipping:
			if each.isalpha():
				skipping	= False
			continue

		if each == '\033':
			skipping	= True
			continue

		if not each.isprintable(): continue
		if (
			each == "\r"
			or each == "\n"
			or each == "\f"
			or each == "\v"
		): continue
		if each == "\t":
			length += 8
			continue
		length += 1
	
	return length

# Support for extended fields
@dataclasses.dataclass
class GSField:
	name:			str
	display_name:	str
	show_in_tree:	bool
	array_persons:	bool
	type:			str

	@property
	def spaced_name(self):
		if hasattr(self, "_spaced_name"):
			return self._spaced_name
		else:
			self._spaced_name	= convert_to_underscores(self.name, ' ')
			return self._spaced_name

	@property
	def value_name(self):
		if hasattr(self, "_value_name"):
			return self._value_name
		else:
			self._value_name	= convert_to_underscores(self.name)
			return self._value_name

	def has_field(self, person):
		return hasattr(person, self.value_name)
	
	def extract(self, person):
		return getattr(person, self.value_name)

EXTENDED_FIELDS:	list[GSField]	= [
	GSField(
		"PlaceOfBirth",
		"Place of Birth",
		False,
		False,
		"Fields:Place"
	),
	GSField(
		"PlaceOfDeath",
		"Place of Death",
		False,
		False,
		"Fields:Place"
	)
]

def all_fields_for_person(person):
	for field in EXTENDED_FIELDS:
		if field.has_field(person):
			yield field

# MARK: Tree handling
# ———————————————————————————

OPTIONS = None
def setup_options():
	global OPTIONS
	global ASCII

	OPTIONS = Graphics.LineDrawing(Graphics.Color.Foreground.YELLOW, ASCII)

setup_options()

class Tree:
	def __init__(self):
		self.lst	: dict	= {}
		self.data	: str	= ""

	def _newlines(self, data, header):
		return data.replace(
			"\n",
			"\n%s"%header
		)

	def _print(self, p: list, last=True, header="", lastcall=False):
		self.data += (
			header
			+ (OPTIONS.ELBOW if last else OPTIONS.TEE)
			+ self._newlines(
				str(p[0]),
				(
					header
					+ (OPTIONS.BLANK if last else OPTIONS.PIPE)
				)
			)
			+ "\n"
		)
		if len(p[1]) != 0:
			children = p[1]
			for i, c in enumerate(children):
				self._print(
					c,
					last = (
						i == len(children) - 1
					),
					header = (
						header									\
						+ (OPTIONS.BLANK if last else OPTIONS.PIPE)
					),
					lastcall = (
						i == len(children) - 1 or last
					)
				)

	def gen(self):
		for each in self.lst:
			self._print(each)

		return self.data

class Diagram:
	def __init__(self):
		self.tree       : dict  = {}
		self.diagram    : str   = ""
		self.ancestor	: bool	= True
		self._treeobj   : Tree  = Tree()
		self.__str__            = self.gen

	@staticmethod
	def colorise_bg(output, color=None):
		output = output.split("\n")
		output2 = []
		output3 = ""

		longest = 0
		for line in output:
			longest = max(longest, actuallen(line))
		
		for line in output:
			spaces = " " * (longest - actuallen(line))
			output2.append(line + spaces)

		for index, line in enumerate(output2):
			output3 += (
				(
					"\n"
					if index != 0
					else ""
				)
				+ (
					Graphics.Decoration.BOLD
					if index == 0
					else ""
				)
				+ (
					Graphics.Color.Foreground.WHITE
					if color != Graphics.Color.Background.DEFAULT
					else ""
				)
				+ color
				+ line
				+ (
					Graphics.Color.Foreground.DEFAULT
					if color != Graphics.Color.Background.DEFAULT
					else ""
				)
				+ Graphics.Color.Background.DEFAULT
				+ (
					Graphics.Decoration.RESETBOLD
					if index == 0
					else ""
				)
			)
		
		output = output3

		return output

	def getinfo(self, person, rootness=100):
		def get_id_fmt(ps):
			return " " + fmt_id(ps, "", "")

		person	= GSPerson.by_id(person)
		name	= person.get_name() + get_id_fmt(person)
		namelen	= len(name)

		output	= "".join([
			name + "\n",
			add_field("Birth", person.birth_date, True, False, namelen),
			add_field("Death", person.death_date, True, False, namelen)
		])

		if not self.ancestor or self.tree.get(person, False):
			for spouse in person.get_spouses():
				output += add_field("Spouse", spouse.get_name()+get_id_fmt(spouse), True, False, namelen)

		for field in all_fields_for_person(person):
			if field.show_in_tree:
				if field.array_persons:
					for psx1 in field.extract(person).split(' '):
						psx1	= GSPerson.by_id(person)
					output += add_field(
						field.display_name,
						psx1.get_name()+get_id_fmt(psx1),
						True,
						False,
						namelen
					)
				
				else:
					output += add_field(
						field.display_name,
						getattr(person, field.value_name),
						True,
						False,
						namelen
					)
		
		output = output.rstrip("\n")

		output = Diagram.colorise_bg(
			output,
			(
				Graphics.Color.Background.BLUE
				if rootness == 0 else
				Graphics.Color.Background.DEFAULT
			)
		)

		return output

	def _convert(self, subdict, recurse=0):
		list = []
		for key in subdict.keys():
			if subdict[key] is None:
				list.append(
					[
						self.getinfo(key, recurse),
						[]
					]
				)
			else:
				list.append(
					[
						self.getinfo(key, recurse),
						self._convert(
							subdict[key],
							recurse+1
						)
					]
				)

		return list

	def gen(self):
		self._treeobj.lst = self._convert(self.tree)

		self.diagram = self._treeobj.gen()
		return self.diagram

# Tree Database Functionality
# ———————————————————————————

def convert_to_underscores(name: str, sep="_"):
	IRREGULAR_CONVERSIONS	= {
		"ID":			"id"
	}

	if name in IRREGULAR_CONVERSIONS:
		return IRREGULAR_CONVERSIONS[name]

	new_name = ""
	for index, char in enumerate(name):
		if char.isupper():
			if index == 0:
				new_name += char.lower()
			else:
				new_name += sep+char.lower()
		else:
			new_name += char
	return new_name

class GSPerson:
	def __init__(
		self,
		dictionary:	dict
    ):
		for item in dictionary:
			setattr(self, convert_to_underscores(item), dictionary[item])

		# Other things
		self.parents	= [int(i) for i in self.parents.split(" ") if i]
		self.gender		= resolve_gender(self.gender)

	def profile(self):
		return "".join([
			# self.get_name
			"%s%s%s\n" % (
				Graphics.Color.Background.BLUE,
				self.get_name(),
				Graphics.Common.RESET
			),

			# self.id
			add_field("ID", self.id),

			# self.birth_date
			add_field("Birth", self.birth_date),

			# self.death_date
			add_field("Death", self.death_date),

			# self.gender
			add_field("Gender", get_gender(self.gender)),

			# extended fields
			*[
				add_field(field.display_name, field.extract(self))
				for field in all_fields_for_person(self)
				if not field.array_persons
			],

			# self.get_parents
			section_with_persons("Parents", self.get_parents),

			# self.get_children
			section_with_persons("Children", self.get_children),

			# self.get_siblings
			section_with_persons("Siblings", self.get_siblings),

			# self.get_spouses
			section_with_persons("Spouses", self.get_spouses),

			# more extended fields
			*[
				section_with_persons(field.display_name, lambda: [
					GSPerson.by_id(psnum)
					for psnum in field.extract(self).split(' ')
				])
				for field in all_fields_for_person(self)
				if field.array_persons
			]
		])

	def get_parents(self):
		arr	= []
		for person in PERSONS:
			if person.id in self.parents: arr.append(person)
		return arr

	def get_children(self):
		arr	= []
		for person in PERSONS:
			if self.id in person.parents: arr.append(person)
		return arr
	
	def _gen_dict(self, person, fc=False):
		current_dict 	= []
		parents		= person.get_parents() if not fc else person.get_children()
		current_dict.append(person.id)
		if len(parents) == 0:
			current_dict.append(None)
		else:
			subdict = {}
			for parent in parents:
				t = self._gen_dict(parent, fc)
				subdict[t[0]] = t[1]
			current_dict.append(subdict)
		return current_dict
	
	def ancestor_tree(self, backend=Diagram):
		root	 		= {}
		root[self.id]	= self._gen_dict(self)[1]

		diagram 			= backend()
		diagram.tree		= root
		return diagram.gen()

	def descendant_tree(self, backend=Diagram):
		root	 		= {}
		root[self.id]	= self._gen_dict(self, fc=True)[1]

		diagram 			= backend()
		diagram.ancestor	= False
		diagram.tree		= root
		return diagram.gen()
	
	@staticmethod
	def by_id(tid):
		for person in PERSONS:
			if person.id == tid:
				return person
		return None
	
	def get_siblings(self):
		arr	= []
		if not self.parents:				return arr

		for person in PERSONS:
			if person.id == self.id:			continue
			if person.parents == self.parents:	arr.append(person)
		return arr
			
	def get_spouses(self):
		spouses = []
		children = self.get_children()
		for child in children:
			other_parent = 0
			for tid in child.parents:
				if int(tid) != self.id:
					other_parent = int(tid)
			spouse = GSPerson.by_id(other_parent)
			if not (
				spouse is None
				or spouse in spouses
			):
				spouses.append(spouse)

		return spouses
	
	def get_name(self):
		return " ".join([i for i in [
			self.title,
			self.first_name,
			self.middle_name,
			self.last_name
		] if i])

class GSFamilyTreeDocument:
	def __init__(self):
		self.persons	= []

	def __postinit__(self):
		global PERSONS
		for person in self.persons:
			PERSONS.append(person)

class GSFamilyTreeDocumentINI(GSFamilyTreeDocument):
	def __init__(self, filename: str):
		DEFAULTS	= {
			"Title":		"",
			"FirstName":	"",
			"MiddleName":	"",
			"LastName":		"",
			"BirthDate":	"",
			"DeathDate":	"",
			"Parents":		"",
			"Gender":		"",
			"Notes":		""
		}

		super().__init__()

		data	= parser_from_ini(filename)

		name: str
		for name in data.sections():
			section	= dict(data[name])

			SectionHeaderError	= "Bad section header format."
			
			if name.isnumeric():
				
				for key in DEFAULTS:
					section.setdefault(key, DEFAULTS[key])

				section["ID"]	= int(name)

				self.persons.append(GSPerson(section))

			else:
				name	= name.split(":")

				if len(name) < 3:
					raise RuntimeError(SectionHeaderError)
				if name[0] != "Gershwin":
					raise RuntimeError(SectionHeaderError)
				
				if name[1] == "Field":
					EXTENDED_FIELDS.append(
						GSField(
							name[2],
							section["DisplayName"],
							get_bool(section.get("ShowInTree", "False")),
							get_bool(section.get("ArrayOfPersons", "False")),
							section.get("Type", "Field:Text")
						)
					)
				
				else:
					raise RuntimeError(SectionHeaderError)

		super().__postinit__()

# MARK: Command Line
# ———————————————————————————

def push_cli_data(name: str, args: list, data: str):
	CLI._state_data	= data
	CLI._state_name	= shlex.join([name] + args)
	diag(data)

def query_list(args: list):
	import re

	person: GSPerson

	def match(str1: re.Pattern, str2: str):
		return bool(str1.match(str2))

	if len(args) == 1 and args[0] == "all":
		diag(table_format(PERSONS))
		return

	MATCHES	= PERSONS
	if len(args) != 2:
		if (len(args) + 1) % 3 != 0:
			return "Bad arguments."
	
	def person_eligible_with_format(person: GSPerson, args):
		# Old-style properties

		if args[0] in {"title", "first name", "middle name", "last name"}:
			ptrn	= re.compile(args[1])

			if args[0] == "title":
				if match(ptrn, person.title):
					return True

			elif args[0] == "first name":
				if match(ptrn, person.first_name):
					return True

			elif args[0] == "middle name":
				if match(ptrn, person.middle_name):
					return True

			elif args[0] == "last name":
				if match(ptrn, person.last_name):
					return True
		
		# if args[0] in {"children", "siblings", ""}
			
		# elif args[0] == "children":
		# 	if p
			
		# New style 'extended values'

		for field in EXTENDED_FIELDS:
			if args[0] == field.spaced_name:
				if match(ptrn, field.extract(person)):
					return True
			
		return False
	
	ARGS_NEW	= []
	CUR_ARGS	= []
	for arg in args:
		if arg == "and":
			ARGS_NEW.append(CUR_ARGS)
			CUR_ARGS	= []
			continue
		
		CUR_ARGS.append(arg)

	ARGS_NEW.append(CUR_ARGS)
	
	for arg_set in ARGS_NEW:
		old_matches	= MATCHES
		MATCHES		= []

		for person in old_matches:
			if person_eligible_with_format(person, arg_set):
				MATCHES.append(person)

	push_cli_data("list", args, table_format(MATCHES))

class CLICommands:
	def clear(args):
		"""Clear the screen/terminal."""
		if len(args) != 0:
			return "Bad arguments."
		else:
			print(Graphics.Common.CLEAR, end="")

	def tree(args):
		"""Display a family tree for ancestors or descendants of a person."""
		arguments	= parse_args(args, 1, 1)

		if "ancestor" in arguments[0]:
			ANCESTOR = True
		elif "descendant" in arguments[0]:
			ANCESTOR = False
		else:
			return "Bad arguments."
		
		person = GSPerson.by_id(int(arguments[1][0]))
		if person is None: 
			return "Could not find person with ID %d"%int(arguments[1][0])
		
		if ANCESTOR: 	tree = person.ancestor_tree()
		else:			tree = person.descendant_tree()

		push_cli_data("tree", args, tree)

	def change_characters(args):
		"""Change the line drawing characters used for trees."""

		arguments	= parse_args(args, 1, 0)

		global ASCII
		if "ascii" in arguments[0]:
			diag("Switching to ASCII line drawing characters...")
			ASCII = True
			setup_options()
		elif "unicode" in arguments[0]:
			diag("Switching to Unicode line drawing characters...")
			ASCII = False
			setup_options()
		else:
			return "Bad arguments."

	def close(args):
		"""Close an open file."""
		parse_args(args, 0, 0)

		if CLI.file is None:
			return "File is not open."
		diag("Closing file %s..."%CLI.file.filename)
		CLI.prompt = "GTREE"
		CLI.file = None
		PERSONS.clear()

	def help(args):
		"""Display a help message."""
		parse_args(args, 0, 0)

		diag("Welcome to GTREE, a simple family tree program. This lists")
		diag("all of the commands available to you from the program.\n")
		FMT = "\033[1m{:>24}\033[0m: {}"
		for command in dir(CLICommands):
			# Private commands
			if not (
				command.startswith("_")
				or (
					command.startswith("__") 
					and command.endswith("__")
				)
			):
				diag(
					FMT.format(
						command,
						getattr(
							CLICommands,
							command
						).__doc__
					)
				)
		diag("\nCopyright: Solomon Wood (C) 2024\nAll rights reserved.")

	def exit(args):
		"""Exit the GTREE shell."""
		if len(args) == 0:
			CLI.status = 0
		else:
			return "Bad arguments."
		
	def print_result(args):
		"""Print the result of the last task to an HTML file."""
		arguments	= parse_args(args, None, 1)
		
		if len(arguments[0]) == 0:
			TYPE	= "standalone"
		else:
			TYPE	= arguments[0][0]
		
		if TYPE not in {"standalone", "inline"}:
			return "Bad arguments."
		
		diag("Printing result of '%s'..." % (
			Graphics.Decoration.BOLD + CLI._state_name + Graphics.Common.RESET
		))

		converter	= ansi2html.Ansi2HTMLConverter(
			dark_bg		= False,
			scheme		= "mint-terminal",
			title		= CLI._state_name,
			inline		= True
		)
		converted	= converter.convert(CLI._state_data, False)
		
		template	= STANDALONEHTML if TYPE == "standalone" else HTML
		template	= template.replace("{Data}", converted)
		template	= template.replace("{Title}", CLI._state_name)
		template	= template.replace("{FamilyTreeName}", FILENAME)
		template	+= "\n"

		with open(arguments[1][0], "w") as file:
			file.write(template)
		
	def list(args):
		"""List persons that match criteria."""
		return query_list(args)
	
	def reload(args):
		"""Reload the current GTREE file."""
		if len(args) != 0:
			return "Bad arguments."
		
		diag("Reloading file %s..."%FILENAME)
		CLICommands.close([])
		CLICommands.open([FILENAME])

	def open(args):
		"""Open a GTREE-formatted '.GTR' file."""
		global FILENAME
		if len(args) != 1:
			return "Bad arguments."
		try:
			FILENAME = resolve_globs(args[0])
			diag("Attempting to open file %s..."%FILENAME)
			CLI.file 	= GSFamilyTreeDocumentINI(FILENAME)
			CLI.prompt 	= os.path.basename(FILENAME)
		except:
			FILENAME = None
			diag("Error opening file:")
			display_exception()
			return "Could not open file '%s'."%args[0]
		
	def profile(args):
		"""Generate a 'profile' of a specific person."""
		if len(args) != 1:
			return "Bad arguments."
		person = GSPerson.by_id(int(args[0]))
		if person is None: 
			return "Could not find person with ID %d"%int(args[0])
		
		push_cli_data("profile", args, person.profile())

class CommandLineInterface:
	def __init__(self):
		self.status:		bool					= True
		self.prompt:		str						= "GTREE"
		self.input:			list					= []
		self.exitstatus:	int						= 0
		self.file:			GSFamilyTreeDocument	= None
		self.selected:		GSPerson				= None # Unused.
		self._state_data:	str						= None
		self._state_name:	str						= ""

	def start(self):
		while self.status:
			self.take_input()

			for cmd in self.input:
				try:
					self.execute_command(cmd)
				
				except:
					diag("Exception escaped from .execute-command:")
					display_exception()
					diag("Continuing...")

				diag("")

	def take_input(self):
		self.prompt = self.prompt[:16]

		self.input = [
			shlex.split(each.strip())
			for each in input(
				Graphics.Decoration.BOLD
				+ "@ "
				+ self.prompt
				+ ((16-len(self.prompt))*" ")
				+ " "
				+ Graphics.Color.Foreground.CYAN,
			).split(
				";"
			)
		]

		print(Graphics.Common.RESET, end="")

	def execute_command(self, cmd):
		if len(cmd) == 0:
			diag("Command is empty, ignoring...")
			return
		
		commandname	= cmd[0]
		alsocmd		= cmd[1:]
		try:
			func		= getattr(CLICommands, commandname)
		except AttributeError:
			func		= None
			ret			= "Currently unavailable"

		if func is not None: ret = func(alsocmd)
		if ret != 0 and ret is not None:
			diag("Command %s raised an error: %s"%(
				commandname,
				ret
			))
		
def cli_main():
	global CLI
	print(Graphics.Common.CLEAR, end="")

	CLI = CommandLineInterface()
	diag(WELCOME)

	CLICommands.open([FILENAME]) if FILENAME is not None else None
	diag("")

	def _():
		global CLI
		try: CLI.start()

		except KeyboardInterrupt:
			diag("")
			def __():
				global CLI
				diag("\033[0mAre you sure that you want to exit GTREE? [Y/N] \033[1;36m", end="")
				val = input()
				print("\033[0m", end="")
				if val.upper().strip() == "Y":
					do_exit(CLI.exitstatus)
				elif val.upper().strip() == "N":
					diag("")
					return _()
				else:
					diag("Please answer Y or N.")
					return __()
				
			return __()

	_()

	do_exit(CLI.exitstatus)

def main(argv=sys.argv):
	global FILENAME

	if len(argv) == 1:
		cli_main()
	elif len(argv) == 2:
		FILENAME = argv[1]
		cli_main()

if __name__ == "__main__":
	main()
