# VLANG
This is my toy language, heavily inspired by [Porth](https://gitlab.com/tsoding/porth)

This is a statically typed language written in python, and compiles to x64 assembly!


# Structs 
vlang supports structures, for now you can load any integer value in a struct:
```cpp
struct server 
    int_64
    int_8
end

55 server.0 write
server.0 load print
>> 55 
```

# Constants
constants get replaced with their stack-equivalent during compilation: 
```cpp
const x "yeet"
x puts // will use STRING_PUSH with x's content
>> yeet
```

# functions 
```js
func print_string int int in
    puts

    // return the number 5
    5 return
end

"hello world\n" print_string print
>> hello world
>> 5
```



# variables
#### Syntax will be improved
```js
// also supports! comments
var x int_16 // provide a type (int float or string for now)

2 x write // writes 2 into x
x load // loads the value stored in x ontop of the stack
```	

# if statements and loops
```js
5 5 == if 
    "5 is indeed equal to 5" puts

else
    // some code
end

while x 5 < do 
    "woah" puts
     x load 1 + x write
end
```

# stack operations
```js
1 1 
// LIST OF VALID OPERATIONS:
+ - * / % > >= < <= ==
```
