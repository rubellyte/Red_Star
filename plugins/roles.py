import asyncio
from discord import InvalidArgument, HTTPException, Forbidden, Colour
from plugin_manager import BasePlugin
from utils import Command, respond, split_message, process_args

class RoleCommands(BasePlugin):
	name = "role_commands"
	
	def activate(self):
		pass
		
	@Command("editrole",
		perms={"manage_server"},
		category="roles",
		syntax= "(role name) [name=string][colour=FFFFFF][hoist=bool][mentionable=bool].\nANALYSIS: Strings can be encapsulated in !\"...\" to allow spaces",
		doc= "Edits the specified role name, colour, hoist (show separately from others) and mentionable properties.\n"
		"WARNING: Options must be specified as option=value. No spaces around `=`.\n"
		"ANALYSIS: Colour can be reset by setting it to 0.")
	async def _editrole(self,data):
		"""
			a command for editing a role.
			!editrole (role name) [name=name][colour=colour][hoist=hoist][mentionable=mentionable]
			name is a string
			colour is a colour object (value converted from hexadecimal string)
			hoist and mentionable are boolean
		"""
		args = process_args(data.content.split())
		if len(args)>1:
			err = True
			for server in self.client.servers:
				for role in server.roles:
					if args[1].lower() == role.name.lower(): #found role
						err = False
						t_dict = {}
						for arg in args[2:]:
							t_arg = arg.split("=")
							if len(t_arg)>1: #beautiful
								if t_arg[0].lower() == "name":
									t_dict["name"] = t_arg[1]
								elif t_arg[0].lower() == "colour":
									t_dict["colour"] = Colour(int(t_arg[1],16))
								elif t_arg[0].lower() == "hoist":
									t_dict["hoist"] = t_arg[1].lower()=="true"
								elif t_arg[0].lower() == "mentionable":
									t_dict["mentionable"] = t_arg[1].lower()=="true"
						if len(t_dict)==0:		#you're wasting my time
							raise SyntaxError
						try:
							await self.client.edit_role(server,role,**t_dict)
						except Forbidden:
							raise PermissionError
						t_string = ""
						for k,v in t_dict.items():
							t_string += k+": "+str(v)+"\n"
						await respond(self.client,data,f"**AFFIRMATIVE. Role {args[1].capitalize()} modified with parameters :**\n ```{t_string}```")
						break
			if err:
				await respond(self.client, data,f"**NEGATIVE. ANALYSIS: no role {args[1].capitalize()} found.**")
		else:
			raise SyntaxError

	@Command("createrole",
		perms={"manage_server"},
		category="roles",
		syntax = "(role name) (base role) [name=string][colour=FFFFFF][hoist=bool][mentionable=bool].\nANALYSIS: Strings can be encapsulated in !\"...\" to allow spaces",
		doc = "Creates a role based on an existing role (for position and permissions), with parameters similar to editrole")
	async def _createrole(self,data):
		"""
			a command for creating a role
			takes names for new role and a role that will be copied for position/permissions
		"""
		args = process_args(data.content.split())
		if len(args)>2:
			err = True
			for server in self.client.servers:
				for role in server.roles:
					if args[2].lower() == role.name.lower():
						err = False
						t_dict = {} 
						#copying the existing role (especially permissions)
						t_dict["name"] = args[1]
						t_dict["permissions"] = role.permissions
						t_dict["colour"] = role.colour
						t_dict["hoist"] = role.hoist
						t_dict["mentionable"] = role.mentionable
						t_dict["position"] = role.position
						for arg in args[3:]:
							t_arg = arg.split("=")
							if len(t_arg)>1: #beautiful
								if t_arg[0].lower() == "name":
									t_dict["name"] = t_arg[1]
								elif t_arg[0].lower() == "colour":
									t_dict["colour"] = Colour(int(t_arg[1],16))
								elif t_arg[0].lower() == "hoist":
									t_dict["hoist"] = t_arg[1].lower()=="true"
								elif t_arg[0].lower() == "mentionable":
									t_dict["mentionable"] = t_arg[1].lower()=="true"							
						t_role = await self.client.create_role(server,**t_dict) 
						try:
							await self.client.move_role(server,t_role,t_dict["position"]) #since I can't create a role with a preset position :T
						except (InvalidArgument, HTTPException, Forbidden): #oh hey, why are we copying this role again?
							await self.client.delete_role(server,t_role)
							await respond(self.client,data,f'**WARNING: Failed to move role {args[1].capitalize()} to position {t_dict["position"]}.**')
							raise PermissionError #yeah, we're not copying this
						t_string = ""
						for k,v in t_dict.items():
							if k != "permissions":
								t_string += k+": "+str(v)+"\n"
							else:
								t_string += k+": "+", ".join({x.upper() for x,y in v if y})+"\n" #woo, permissions
						await respond(self.client,data,f"**AFFIRMATIVE. Created role {args[1].capitalize()} with parameters :**\n ```{t_string}```")
						break
			if err:
				await respond(self.client,data,f"**NEGATIVE. ANALYSIS: no base role {args[2].capitalize()} found.**")
		else:
			raise SyntaxError

	@Command("deleterole",
		perms = {"manage_server"},
		category = "roles",
		syntax = "(role name) [position].\nANALYSIS: Strings can be encapsulated in !\"...\" to allow spaces",
		doc = "Deletes first encounter of the role with the given name and optionally position.")
	async def _deleterole(self,data):
		"""
			what do you think it does
		"""
		args = process_args(data.content.split())
		if len(args)>1:
			err = True
			pos = -1
			if len(args) > 2:
				try:
					pos = int(args[2])
				except ValueError:
					raise SyntaxWarning
			for server in self.client.servers:
				for role in server.roles:
					if (args[1].lower() == role.name.lower())and(((pos>=0)and(role.position == pos))or pos<0): #delete if name matches, and if pos is not -1 - if position matches
						err = False
						t_position = role.position
						try:
							await self.client.delete_role(server,role)
						except Forbidden:
							raise PermissionError
						else:
							await respond(self.client,data,f"**AFFIRMATIVE. Deleted role: {args[1].capitalize()} in position: {str(t_position)}.**")
						break
			if err:
				await respond(self.client,data,f"**NEGATIVE. ANALYSIS: no role {args[1].capitalize()} found.**")
		else:
			raise SyntaxError
			
	@Command("moverole",
		perms = {"manage_server"},
		category = "roles",
		syntax = "(role name) (position).\nANALYSIS: Strings can be encapsulated in !\"...\" to allow spaces",
		doc = "Moves a role to a provided position.\nWARNING: position must be below the bot role position.")
	async def _moverole(self,data):
		"""
			moves a role to a designated position
		"""
		args = process_args(data.content.split())
		if len(args)>2:
			err = True
			new_position = 0
			try:
				new_position = int(args[2])
			except ValueError:
				raise SyntaxError
			for server in self.client.servers:
				for role in server.roles:
					if args[1].lower() == role.name.lower():
						err = False
						t_position = role.position
						# TODO : figure out a way to check position-based permissions without trying and getting an error
						try:
							await self.client.move_role(server,role,new_position)
						except (InvalidArgument, HTTPException, Forbidden):
							await respond(self.client,data,f'**WARNING: Failed to move role {args[1].capitalize()} to position {new_position}.**')
							raise PermissionError
						else:
							await respond(self.client,data,f"**AFFIRMATIVE. Moved role {args[1].capitalize()} from position {t_position} to {new_position}.**")
						break
			if err:
				await respond(self.client,data,f"**NEGATIVE. ANALYSIS: no role {args[1].capitalize()} found.**")
		else:
			raise SyntaxError
	
	@Command("inforole",
		category = "roles",
		syntax = "(role name).\nANALYSIS: Strings can be encapsulated in !\"...\" to allow spaces",
		doc = "Returns all the info about the given role.")
	async def _inforole(self,data):
		"""
			provides an infodump of a role, including permissions and position
		"""
		args = process_args(data.content.split())
		if len(args)>1:
			err = True
			for server in self.client.servers:
				for role in server.roles:
					if args[1].lower() == role.name.lower():
						err = False
						t_dict = {}
						t_dict["name"] = role.name
						t_dict["permissions"] = role.permissions
						t_dict["colour"] = role.colour
						t_dict["hoist"] = role.hoist
						t_dict["mentionable"] = role.mentionable
						t_dict["position"] = role.position
						t_dict["created_at"] = role.created_at
						t_string = ""
						for k,v in t_dict.items():
							if k != "permissions":
								t_string += k+": "+str(v)+"\n"
							else:
								t_string += k+": "+", ".join({x.upper() for x,y in v if y})+"\n" #woo, permissions
						await respond(self.client,data,f"**ANALYSIS: role {args[1].capitalize()} has parameters :**\n ```{t_string}```")
						
			if err:
				await respond(self.client,data,f"**NEGATIVE. ANALYSIS: no role {args[1].capitalize()} found.**")
		else:
			raise SyntaxError
	
	@Command("listrole",
		category = "roles",
		doc = "Lists all roles.")
	async def _listrole(self,data):
		"""
			lists all roles along with position and color
		"""
		t_string = "**AFFIRMATIVE. Listing roles :**\n"
		for server in self.client.servers:
			for role in server.roles:
				t_string += f"`{role.name[:40].ljust(40)} [{role.position} | {role.colour}]`\n"
		for t in split_message(t_string):
			await respond(self.client,data,t)