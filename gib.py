######################################################################
# gibberish.py - python gibberish interpreter 
# 
# possible inconsistencies:
#   - q(3) stops the entire program, not just the currently running
#     piece of code, even when called from an exec'ed string
#     (I took "currently-running program" to mean the entire program)
#
#   - not in specification, but unfinished official interpreter seems to 
#     do it this way and/or given examples seem to rely on this:
#     - trying to copy/move/pop past the stack results in a run-time error
#     - numbers are floating point
#     - numbers used for stack indexes are rounded down
#     - type mismatches are run-time errors
#     - the stack and selected instruction set are global across "subroutines"
#     - pushing a string constant [like this] counts as one instruction 
#     - using x(0) to set the instruction set to one that doesn't exist
#       is a run-time error       
#
#   - neither in specification or in unfinished official interpreter
#     - but seems logical:
#       - exec'ing a string of malformed code is a run-time error
#
#       - numbers used for string indexes are rounded down
#         (like the stack)
# 
#       - reading past EOF returns -1 (char) or "" ([]?) (str)
#         (most other esolangs return -1 on EOF) 
#
#       - a line read from stdin still has its newline attached
#         (to distinguish [\n] (=empty line) from [] (=EOF), 
#          also this is how almost everyone else does it)
#
#       - logical operators consider 0.0000... to be false and everything
#         else to be true
#      
#     - and I have no idea how else to do it:
#       - lshift and rshift convert their arguments to ints first
#         (can't shift something, say, 2.3 bits to the left,
#          and bitshifting IEEE-754 floating point values seems monumentally
#          useless in comparison with bitshifting ints)
#
#       - arguments to binary and/or are converted to ints first
#         (fits with lshift/rshift)
#
##########################################


from operator import *
import sys

# types used for strings and numbers
STRT = str
NUMT = float

### helper functions ###
def typedesc(type):
   if type==STRT: return "string"
   if type==NUMT: return "number"
   return "invalid (%s)"%str(type)

# make error string
def errstr(code, error, position):
   amt = max(0, position - 5)
   prev = code[amt : position]
   if amt!=0: prev = "..." + prev
   
   amt = min(position + 6, len(code))
   next = code[position+1 : amt]
   if amt!=len(code): next += "..."
   
   return "%s at position %d (%s ->%s<- %s)" % \
         (error, position, prev, code[position], next)

# make error string with list of items
def items_errstr(code, error, position):
   prev = ",".join([str(c) for c in code[max(0, position - 5) : position]])
   next = ",".join([str(c) for c in code[position+1:position+6]])

   return "%s at ip %s (%s ->%s<- %s)" % \
         (error, position, prev, str(code[position]), next)
         

# return ordinal suffix (i.e. 1 => st and 4 => th)
def ordsuffix(num):
   if (int(num) % 100 in (11,12,13)): return "th"
   if (int(num) % 10 == 1): return "st"
   if (int(num) % 10 == 2): return "nd"
   if (int(num) % 10 == 3): return "rd"
   return "th"

#####

# stack class
class Stack:

   stack = None
   
   def __init__(self, copystack=None):
      if copystack:
         self.stack = copystack[:]
      else:
         self.stack = []


   def push(self, value):
      # make sure all numbers use the same type
      if type(value) in [bool, int]: value = NUMT(value)
      self.stack.append(value)
 
   def pop(self):
      return self.stack.pop()

   def swapn(self, n):
      n=int(n)
      foo = self.stack[-1-n]
      self.stack[-1-n] = self.stack[-1]
      self.stack[-1] = foo

   swap = lambda s: s.swapn(1)
   swap2 = lambda s: s.swapn(2)
   swap3 = lambda s: s.swapn(3)
 
   def copy(self, n):
      n=int(n)
      self.stack.append(self.stack[-1-n])

   dup = lambda s: s.copy(0)
   
   def move(self, n):
      n=int(n)
      self.stack.append(self.stack[-1-n])
      del self.stack[-1-n]

   def insert(self, n, value):
      n=int(n)
      self.stack.insert(-n-1, value)

   # 'inverted' copy/move = copy/move counting from the bottom of the stack
   def invcopy(self, n):
      n=int(n)
      self.stack.append(self.stack[n])
   
   def invmove(self, n):
      n=int(n)
      self.stack.append(self.stack[n])
      del self.stack[n]

   # getitem/setitem/len
   def __getitem__(self, n):
      return self.stack[-1-n]
   def __setitem__(self, n, val):
      self.insert(n, val)
   def __len__(self):
      return len(self.stack)


# parser
class Parser:
   CONSTANT, COMMAND = range(2)

   # program will be made up of a list of these
   class Item:
      def __init__(self, type, value):
         if type in (Parser.CONSTANT, Parser.COMMAND):
            self.type=type
            self.value=value
         else: raise TypeError, "item type invalid: %d" % type
      
      def __str__(self):
         if self.type==Parser.COMMAND: return self.value
         elif self.type==Parser.CONSTANT:
            if isinstance(self.value, str): return "[%s]" % self.value
            else: return str(self.value)

   # takes string, returns list of items
   @staticmethod
   def parse(string):
      items = []
      i = 0
      while i<len(string):
         # numbers
         if string[i] in "0123456789": 
            items.append(Parser.Item(Parser.CONSTANT, NUMT(string[i])))
         # strings
         elif string[i] == '[':
            curstr = ''
            lvl = 1
            while lvl>0:
               i += 1
               if (i>=len(string) and lvl>0):
                  raise ValueError(errstr(string, "unterminated [", i-1))
               if string[i] == ']': lvl -= 1
               elif string[i] == '[': lvl += 1
               if (lvl!=0): curstr += string[i]
            items.append(Parser.Item(Parser.CONSTANT, curstr))
         # whitespace is ignored
         elif string[i] in ' \n\t': pass
         # ] without [ == error
         elif string[i] == ']':
            raise ValueError(errstr(string, "] without [", i))
         # not one of these == command
         else:
            items.append(Parser.Item(Parser.COMMAND, string[i]))
         i += 1
   
      return items

class Interpreter:

   # exception to be caught if something goes wrong with the code
   class CodeError(Exception): pass;

   world = None
   code = None
   stack = None
   ip = 0
   activeset = 0
   sets = None # command sets, see init
   parent = None

   def __init__(self,world,code,stack=None,ip=0,activeset=0,parent = None):
      self.world = world
      self.code = code
      if stack==None:
         self.stack = Stack()
      else:
         self.stack = stack
      self.ip = ip 
      self.activeset = activeset
      self.parent = None

      s=self # makes the huge list less long
      s.sets = [
          # instruction set 0 #
          { 'e' : s.activateSet1,
            'f' : s.activateSet2,
            'g' : s.activateSet3,
            'x' : s.cActivateSet,
            'j' : s.cGetSet,
            'z' : s.cNop
          },
          # instruction set 1 #
          { 'u' : s.cDuplicate,
            'a' : s.cAdd,
            's' : s.cSub,
            'm' : s.cMul,
            'd' : s.cDiv,
            't' : s.cToStr,
            'i' : s.cToNum,
            'c' : s.cConcatenate,
            'o' : s.cOutput,
            'q' : s.cInlineOutput,
            'n' : s.cReadChar,
            'l' : s.cReadLine,
            'h' : s.cSubstring,
            'y' : s.cStrLen,
            'v' : s.cDiscard,
            'p' : s.cCopy,
            'k' : s.cMove,
            'r' : s.cStackSize
          },
          # instruction set 2 #
          { 'u' : s.cGT,
            'd' : s.cLT,
            's' : s.cSkip, 
            't' : s.cSkipTwo,
            'p' : s.cInsert,
            'a' : s.cAnd,
            'o' : s.cOr,
            'n' : s.cNot,
            'c' : s.cExec,
            'w' : s.cWhile,
            'q' : s.cEqual,
            'l' : s.cLshift,
            'r' : s.cRshift
          },
          # instruction set 3 #
          { 'q' : s.cQuit,
            'w' : s.cRecallWhile,
            'n' : s.cIsNumber,
            's' : s.cIsString,
            'a' : s.cBinAnd,
            'o' : s.cBinOr,
            'i' : s.cInteger,
            'm' : s.cMod,
            't' : s.cToChar,
            'c' : s.cCharAt,
            'r' : s.cReplaceChar, 
            'p' : s.cInvertedCopy,
            'k' : s.cInvertedMove, 
            'b' : s.cSwap,
            'd' : s.cSwap2,
            'h' : s.cSwap3,
          }
      ]
 
   # step function
   # returns True if there are more steps, False if not.
   def step(self):
      if self.ip >= len(self.code):
         return False # at the end of the code
      
      curitem = self.code[self.ip]
 
      # if there's a trace variable defined and true, give a trace
      try: 
         global trace
         if trace: 
            print "\x1b[7m",  
            print "trace: cur=", self.ip, str(curitem), "set=", self.activeset, "stack=", self.stack.stack,
            print "\x1b[0m"
      except: pass

      if curitem.type == Parser.CONSTANT:
         # this is a constant value, push it
         self.sf(self.stack.push, [curitem.value])
      else:
         # it's a command
         if curitem.value in self.sets[0]:
            # command set 0 has priority above everything
            self.sets[0][curitem.value]()
         else:
            # get it from selected set
            if self.activeset<0 or self.activeset>=len(self.sets):
               # selected set is invalid
               raise Interpreter.CodeError(self.err("no such set: %d",
                                               self.activeset))
            else:
               if not curitem.value in self.sets[self.activeset]:
                  #invalid command for selected set
                  raise Interpreter.CodeError(self.err(
                         "set %d has no command '%s'"%( self.activeset, \
                                                   curitem.value)))           
               else:
                  #yay it's good, run it
                  try:
                     self.sets[self.activeset][curitem.value]()
                  except ZeroDivisionError, complaint:
                     raise Interpreter.CodeError(self.err(
                         "division by zero (%s)"%complaint))
      self.ip += 1  
      return True   

   # make an error string with error & current state
   def err(self, error):
      return items_errstr(self.code, error, self.ip)


   # call stack function and catch its errors
   def sf(self, func, args):
      rv=None
      try: rv = func(*args)
      except IndexError, complaint:
         raise Interpreter.CodeError(self.err("stack error (%s)"%complaint))
      return rv

   # raise a type error
   def raiseTypeErr(self, expected, got):
      raise Interpreter.CodeError(
          self.err("wrong type: expected %s instead of %s" % \
                      (typedesc(expected), typedesc(got))))
     
   ### commands ###
   
   # convert a function f(a) into push(f(pop())) + type checking
   def unarystackf(self, f, ntype=None, pushresult=True):
      def stackfunc():
         a=self.sf(self.stack.pop,[])
         if ntype and not isinstance(a,ntype):
            self.raiseTypeErr(ntype, type(a))

         res = f(a)
         if pushresult: self.sf(self.stack.push,[res])
      return stackfunc

   # convert a function f(a,b) into b=pop(),a=pop(),push(f(a,b)) + type checking
   def binstackf(self, f, atype=None, btype=None, pushresult=True):
      def stackfunc():
         b = self.sf(self.stack.pop,[])
         a = self.sf(self.stack.pop,[])
         if btype and not isinstance(b, btype):
            self.raiseTypeErr(btype, type(b))
         if atype and not isinstance(a, atype):
            self.raiseTypeErr(atype, type(a))
         res=f(a,b)
         if pushresult: self.sf(self.stack.push,[res])
      return stackfunc
   
   # and now one with three arguments f(a,b,c) 
   def tristackf(self, f, atype=None, btype=None, ctype=None, pushresult=True):
      x = self.sf
      y = self.stack.pop
      def stackfunc():
         c = x(y,[])
         b = x(y,[])
         a = x(y,[])
         if ctype and not isinstance(c,ctype):
            self.raiseTypeErr(ctype, type(c))
         if btype and not isinstance(b,btype):
            self.raiseTypeErr(btype, type(b))
         if atype and not isinstance(a,atype): 
            self.raiseTypeErr(atype, type(a))
         res = f(a,b,c)
         if pushresult: self.sf(self.stack.push,[res])
      return stackfunc 
        
   ## set 0 ##
   def cActivateSet(self):
      set = self.sf(self.stack.pop,[])
      if not isinstance(set, NUMT):
         raise Interpreter.CodeError(
                               self.err("wrong type: expected number"))
      if len(self.sets)<=int(set) or int(set)<0: 
         raise Interpreter.CodeError(
                               self.err("no instruction set %d exists" % set))
      self.activeset = int(set)
   
   def activateSet1(self): self.activeset = 1
   def activateSet2(self): self.activeset = 2
   def activateSet3(self): self.activeset = 3

   def cGetSet(self):
      self.sf(self.stack.push,[self.activeset])
 
   def cNop(self): pass

   ## set 1 ##
   def cDuplicate(self): self.sf(self.stack.dup,[])
   def cAdd(self): self.binstackf(add, NUMT, NUMT)()
   def cSub(self): self.binstackf(sub, NUMT, NUMT)()
   def cMul(self): self.binstackf(mul, NUMT, NUMT)()
   def cDiv(self): self.binstackf(div, NUMT, NUMT)()

   # shortest representation of value in string
   def v2str(self, n):
      if n=="": return n
      if isinstance(n,str) and (n[0]==' ' or n[-1]==' '): return n
      try: v=str(int(n))
      except:
         try: v=str(float(n))
         except: v=str(n)
      return v

   def cToStr(self): self.unarystackf(self.v2str, NUMT)()
   def cToNum(self): 
      def tonum(s):
         # return a number from the string if possible,
         # if not a valid number then push the string back
         try: n = NUMT(s)
         except ValueError: n = s
         return n
      self.unarystackf(tonum, STRT)()
   def cConcatenate(self): self.binstackf(add, STRT, STRT)() 
   def cOutput(self):             
      self.unarystackf(
             (lambda s:self.world.out(self.v2str(s)+"\n")),pushresult=False)()
   def cInlineOutput(self): 
      self.unarystackf(
             (lambda s:self.world.out(self.v2str(s))),pushresult=False)()
   def cReadChar(self): 
      self.sf(self.stack.push, [NUMT(self.world.readchar())])
   def cReadLine(self):
      self.sf(self.stack.push, [self.world.readline()])
     
   def cSubstring(self):
      self.tristackf((lambda strn,start,end:strn[int(start):int(end)]),
                             STRT,NUMT,NUMT)()
   def cStrLen(self): self.unarystackf(len, STRT)()
   def cDiscard(self): self.sf(self.stack.pop, [])
   def cCopy(self): self.unarystackf(self.stack.copy, NUMT, False)()
   def cMove(self): self.unarystackf(self.stack.move, NUMT, False)()
   def cStackSize(self):
      self.sf(self.stack.push, NUMT(len(self.stack)))
   
   ## set 2 ##
   def cGT(self): self.binstackf(gt)()
   def cLT(self): self.binstackf(lt)()
   def cSkip(self):
      def skip(n): self.ip += int(n)
      self.unarystackf(skip,NUMT,False)()
   def cSkipTwo(self):
      def skip2(n): self.ip += int(n*2)
      self.unarystackf(skip2,NUMT,False)()
   def cInsert(self):
      def insert(thing, where): self.stack.insert(where, thing)
      self.binstackf(insert, btype=NUMT, pushresult=False)()
   def cAnd(self): self.binstackf(lambda a,b:NUMT(a and b and 1 or 0))()
   def cOr(self): self.binstackf(lambda a,b:NUMT((a or b) and 1 or 0))()
   def cNot(self): self.unarystackf(lambda a:NUMT(not a and 1 or 0))()
   
  
   def execstr(self, codestr):
      self.world.recurse(self, codestr)

   def cExec(self): self.unarystackf(self.execstr,STRT,False)()
   def cWhile(self):
      while True:
         # pop a value
         val = self.sf(self.stack.pop,[])
         if val: 
            # pop code, run it
            code = self.sf(self.stack.pop,[])
            if not isinstance(code, STRT):
               self.raiseTypeErr(STRT, type(code))
            else:
               self.execstr(code)
         else:
            break
   def cEqual(self): self.binstackf(eq)()
   def cLshift(self): self.binstackf((lambda a,b:int(a)<<int(b)),NUMT,NUMT)()
   def cRshift(self): self.binstackf((lambda a,b:int(a)>>int(b)),NUMT,NUMT)()
   
   ## set 3 ##
  
   def cQuit(self): self.world.quit()
   def cRecallWhile(self):
      # pop code
      code = self.sf(self.stack.pop,[])
      if not isinstance(code, STRT): self.raiseTypeErr(STRT, type(code))
      # while
      while self.sf(self.stack.pop,[]):
         self.execstr(code)
   
   def cIsNumber(self):
      self.unarystackf(lambda v: isinstance(v,NUMT) and 1 or 0)()
   def cIsString(self):
      self.unarystackf(lambda v: isinstance(v,STRT) and 1 or 0)()
   # binary and/or use integers again
   def binop(self,op): return lambda a,b: op(int(a), int(b))
   def cBinAnd(self): self.binstackf(self.binop(and_), NUMT, NUMT)()
   def cBinOr(self): self.binstackf(self.binop(or_), NUMT, NUMT)()
   def cInteger(self): self.unarystackf(int, NUMT)()
   def cMod(self): self.binstackf(mod, NUMT, NUMT)()
   def cToChar(self): self.unarystackf((lambda k:chr(int(k)%256)), NUMT)()
   def cCharAt(self): 
      def charat(strn, idx):
         idx=int(idx)
         if (idx<0 or idx>=len(strn)):
            # nowhere in the spec it says python-style negative indexes
            # are allowed...
            raise Interpreter.CodeError(self.err(
                   ("index out of bounds: tried to get %d-char string's " +\
                    "%d%s character") % (len(strn), idx, ordsuffix(idx)) ))
         return NUMT(ord(strn[idx]))
      self.binstackf(charat, STRT, NUMT)()
   def cReplaceChar(self):
      def replacechar(strn, idx, repl):
         idx=int(idx)
         if (idx<0 or idx>=len(strn)):
            raise Interpreter.CodeError(self.err(
                   ("index out of bounds: tried to change %d-char string's "+\
                    "%d%s character") % (len(strn), idx, ordsuffix(idx)) ))
         return strn[:idx] + repl[0] + strn[idx+1:]
      self.tristackf(replacechar, STRT, NUMT, STRT)()
   def cInvertedCopy(self):
      self.unarystackf(self.stack.invcopy, NUMT, False)()
   def cInvertedMove(self):
      self.unarystackf(self.stack.invmove, NUMT, False)()
   def cSwap(self): self.sf(self.stack.swap, [])
   def cSwap2(self): self.sf(self.stack.swap2, [])
   def cSwap3(self): self.sf(self.stack.swap3, [])


     
# class World
# handles stepping of interpreter and input and output
#   World().quit() -> ends program
#   World().out("blah") -> stdout.write("blah")
#   World().readchar() -> read 1 char from stdin
#   World().readline() -> read 1 line from stdin

class World:
   interpreter = None

   def __init__(self, codestr, prevint=None):
      # parse the code
       
      self.code = Parser.parse(codestr)
      
  
      if prevint:
         self.interpreter = Interpreter( self, self.code, 
                                         parent=prevint,
                                         stack=prevint.stack,
                                         activeset=prevint.activeset )
      else:
         self.interpreter = Interpreter( self, self.code )
   
   # run the interpreter until it fails or quits
   def run(self):
      
      while self.interpreter.step(): pass
     

   # the interpreter calls these for program control
   def quit(self):
      sys.exit(0)
   
   def out(self, string):
      sys.stdout.write(string)

   def readchar(self):
      v = sys.stdin.read(1)
      if not v: return -1
      else: return ord(v)

   def readline(self):
      return sys.stdin.readline()

   def recurse(self, prevint, codestr):
      try:
         # run the sub-interpreter in its own world
         w = World(codestr, prevint=prevint)
         w.run()
      except ValueError, complaint:
         # parsing failed
         raise Interpreter.CodeError(prevint.err(
                  "exec: parsing of string failed: \n\t%s\n" % complaint))
      except Interpreter.CodeError, complaint:
         # run-time error in code
         raise Interpreter.CodeError(prevint.err(
                  "exec: sub-interpreter runtime error: \n\t%s\n" % complaint))
      except Exception, complaint:
         # something else went wrong
         raise Interpreter.CodeError(prevint.err(
                  "exec: sub-interpreter failed: %s" % str(complaint)))


###############################################################

# start the program
def main(argv):
   global trace
   if (not len(argv) in (2,3)) or (len(argv)==3 and \
                      (not argv[1] == '-trace')): 
      print "usage: %s [-trace] filename | -" % argv[0]
      sys.exit(2)
   else:
      if argv[1]=='-trace': 
         trace=True
         fname = argv[2]
      else:
         trace = False
         fname = argv[1]
      try:
         if fname=='-': f = sys.stdin
         else: f = file(fname, 'r')
      except:
         print "Can't open file %s" % argv[1]
         sys.exit(3)
      code = f.read()
      f.close()
         
      try:
         w = World(code)
         w.run()
      except Interpreter.CodeError, complaint:
         print "Run-time error: %s" % complaint
      except ValueError, complaint:
         print "Parse error: %s" % complaint
      except Exception, complaint:
         print "An exception occured: %s" % complaint

if __name__=="__main__": main(sys.argv)
