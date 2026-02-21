import os
import re
import io
import sys
import time
import json
import math
import shutil
import inspect
import warnings
import importlib
from lxml import etree
from pyflakes.api import checkPath
from pyflakes.reporter import Reporter

sys.setrecursionlimit(10**6)

TxmlDirPath="."
scriptDIR=os.path.dirname(os.path.abspath(__file__))
inheritRecordFilePath=f"{time.time()}_inherit.json"
Krettypes={}
indexxmlRoot=None

def isModule(name):
    try:
        obj=getFinallyObj(name)
        return inspect.ismodule(obj)
    except:
        return False

def getFinallyObj(name,rootModule="cv2"):
    paths = name.split(".")
    obj = importlib.import_module(rootModule)
    for p in paths:
        obj = getattr(obj, p)
    return obj

def isClass(name):
    paths = name.split(".")
    obj = importlib.import_module("cv2")
    for p in paths:
        obj = getattr(obj, p)
    return inspect.isclass(obj)


def isFunc(name):
    paths = name.split(".")
    obj = importlib.import_module("cv2")
    for p in paths:
        obj = getattr(obj, p)
    return callable(obj)


def getOtherType(name):
    paths = name.split(".")
    obj = importlib.import_module("cv2")
    for p in paths:
        obj = getattr(obj, p)
    return type(obj)

knowTypes={}

def getType(name):
    global knowTypes
    ntype=None
    if name in knowTypes:
        return knowTypes[name]
    elif isModule(name):
        ntype = "module"
    elif isClass(name):
        ntype = "class"
    elif isFunc(name):
        ntype = "func"
    else:
        ntype = getOtherType(name)
        if ntype == type(str.__init__):
            ntype="func"
    knowTypes[name] = ntype
    return ntype


def isExist(name):
    paths = name.split(".")
    obj = importlib.import_module("cv2")
    try:
        for p in paths:
            obj = getattr(obj, p)
        return True
    except:
        return False

def finddocfilefromxml(cppname,indexPath):
    root=indexxmlRoot
    nameIndex=cppname.rfind("::")
    classname=cppname[:nameIndex]
    l1=root.xpath(f"compound/name[text()='{classname}']")
    if len(l1)==1:
        compoundTag=l1[0].getparent()
        targetIDs=[]
        targetName=cppname[nameIndex+2:].replace(" ","")
        memberNames = compoundTag.xpath(f"member/name[text()='{targetName}']")
        for memberName in memberNames:
            targetIDs.append(memberName.getparent().get("refid"))

        return targetIDs
    elif len(l1)==0:
        return None
    else:
        print("error: match multiple doc!!!!!!!!!")
        return None

def gettypefromCXXtypes(CXXtypesTopylist,CXXtype):
    for key in CXXtypesTopylist:
        if CXXtype in CXXtypesTopylist[key]:
            return key
    return None

def cvtCXXToPYtype(CXXtpyestr0,tpyeisAnyListfile="CXXtypelist.txt",CXXtypesFile="CXXtypes.json"):
    CXXtypestr=CXXtpyestr0.removeprefix("const").rstrip("*").rstrip("&").strip()
    
    with open(tpyeisAnyListfile) as f:
        lines=f.readlines()
        tpyeisAnyList=[i.strip() for i in lines]
    with open(CXXtypesFile) as f:
        CXXtypesTopylist=json.loads(f.read())

    t=gettypefromCXXtypes(CXXtypesTopylist,CXXtypestr)
    if t!=None:
        return t
    elif CXXtpyestr0 in tpyeisAnyList:
        return "typing.Any"
    else:
        print(f"warning: noknown type: {CXXtypestr}")
        return "typing.Any"

def getFuncInfos(cppname,xmlDirPath):
    """
    如果没有相关文档则返回[]
    ret=[
            {
            "static":False,
            "retType":"...",
            "overload":False,
            "argInfo":{
                "argName":{"type":type, "doc":""},
                ....
                },
            "doc":""
            },
            {...}
        ]
    """
    indexPath=os.path.join(xmlDirPath,"index.xml")
    refids=finddocfilefromxml(cppname,indexPath)
    retOverLoad=False

    if refids==None:
        return []
    if len(refids)>1:
        retOverLoad=True

    rets=[]
    for refid in refids:
        ret={
                "overload":retOverLoad,
                "static":False,
                "argInfo":{}
                }
        targetXmlFilePath=os.path.join(xmlDirPath,refid[:refid.rfind("_")])+".xml"
        root=indexxmlRoot

        memberdefs=root.xpath(f"compounddef/sectiondef/memberdef[@id='{refid}' and @prot='public']")
        if memberdefs==[]:
            continue
        memberdef=memberdefs[0]

        retType=''.join(memberdef.xpath("type")[0].itertext())
        ret["retType"]=retType.strip()

        if memberdef.get("static")=="yes":
            ret["static"]=True

        for param in memberdef.xpath("param"):
            count=0
            paramName=f"arg{count}"
            while paramName in ret["argInfo"]:
                count+=1
                paramName=f"arg{count}"

            decnames=param.xpath("declname")
            if decnames!=[]:
                paramName=''.join(decnames[0].itertext())
            paramType=''.join(param.xpath("type")[0].itertext())
            parameternameTags = memberdef.xpath(f"detaileddescription/para/parameterlist/parameteritem/parameternamelist/parametername[text()='{paramName}']")
            
            paramDoc=""
            if parameternameTags!=[]:
                paramDocTags=parameternameTags[0].getparent().getparent().xpath("parameterdescription/para")
                if paramDocTags!=[]:
                    paramDoc=''.join(paramDocTags[0].itertext())

            ret["argInfo"][paramName]={"type":paramType,"doc":paramDoc}

        doc=""
        briefparaTags=memberdef.xpath("briefdescription/para")
        if briefparaTags!=[]:
            doc=''.join(briefparaTags[0].itertext())
        ret["doc"]=doc
        rets.append(ret)

    return rets


def getPySignList(rootPath):
    with open(os.path.join(rootPath, "modules/python_bindings_generator/pyopencv_signatures.json")) as f:
        j = json.loads(f.read())
    d = []
    for i in j:
        for ii in j[i]:
            newii = ii
            newii["name"] = ii["name"][3:]
            newii["cppname"] = i
            d.append(newii)
    newd = []
    for i in d:
        if isExist(i["name"]):
            newd.append(i)
    return newd


def cvtFuncJsonToPy(jSignDict):
    ret = "def "
    ret += jSignDict["name"].split('.')[-1]
    strArg = jSignDict["arg"].replace(']', "")
    indexs = [m.start() for m in re.finditer(r"\[, ", strArg)]
    index=strArg.find("[, ")
    for _ in range(len(indexs)):
        index += 3
        while index < len(strArg) and re.match(r"[a-zA-Z_0-9]", strArg[index]):
            index += 1
        if index == len(strArg):
            strArg += "=..."
        else:
            strArg = strArg[:index]+"=..."+strArg[index:]
        index+=3
        index=strArg.find("[, ",index)
    strArg = strArg.replace('[', "")
    if strArg.startswith(", "):
        strArg=strArg[2:]
    strFuncRet=jSignDict["ret"]
    
    if len(strFuncRet.split(','))>1:
        strFuncRet="tuple["+strFuncRet+']'

    ret += f"({strArg}) -> {strFuncRet}: ..."
    return ret


def cvtClassJsonToPy(jSignDict):
    return f"class {jSignDict["name"].split('.')[-1]}"


def cvtConstJsonTopy(jSignDict):
    jtype = getOtherType(jSignDict["name"])
    ret = f"{jSignDict["name"]}:{jtype.__name__}=..."
    return ret


def cvtJsonToPy(jSignDict):
    if "ret" in jSignDict:
        return cvtFuncJsonToPy(jSignDict)
    elif "value" in jSignDict:
        return cvtConstJsonTopy(jSignDict)
    else:
        return cvtClassJsonToPy(jSignDict)

def TryCreateFile(filePath):
    if os.path.exists(filePath):
        return
    dirname=os.path.dirname(filePath)
    basePyiPath=os.path.join(scriptDIR,"base.pyi")
    if dirname!="":
        os.makedirs(dirname,exist_ok=True)
    f=open(filePath,"a+")
    f.seek(0)
    txt=f.read()
    if txt=="":
        with open(basePyiPath) as basef:
            f.write(basef.read())
    f.close()

def writeclass(child,filePath):
    TryCreateFile(filePath)
    l=child["name"].split(".")
    classl=child["classl"]
    insertIndex=0
    strTAB=""
    with open(filePath) as f:
        content=f.read()
    if classl!=[]:
        strTAB=' '*4*len(classl)
        for tclassName in classl:
            insertIndex=content.find(f"class {tclassName}",insertIndex)
        insertIndex=insertIndex+1+content[insertIndex+1:].find('\n')
        elipIndex=content.rfind(" ...",insertIndex-5,insertIndex)
        if elipIndex!=-1:
            removeFileStr(filePath,elipIndex,elipIndex+3)
            insertIndex-=4
    else:
        insertIndex=len(content)

    writeClassStr=strTAB
    if l!=[]:
        writeClassStr+=f"class {l[-1]}"
    else:
        writeClassStr+=f"class {child['name']}"

    finobjs=getFinallyObj(child["name"]).__bases__

    finobjNames=child["baseClassl"]
    if finobjNames!=[]:
        for i in finobjs:
            recordInherit(filePath,i.__module__,i.__name__)
        writeClassStr+=f"({','.join(finobjNames)})"

    writeClassStr+=": ...\n"
    insertText(filePath,insertIndex+1,writeClassStr)

def recordInherit(filePath,inherit,classname):
    with open(inheritRecordFilePath,"r+") as f:
        content=f.read()
    j={}
    if content!="":
        j=json.loads(content)
    
    filePath=os.path.normpath(filePath)
    if filePath not in j:
        j[filePath]={}

    if inherit not in j[filePath]:
        j[filePath][inherit]=classname

    jstr=json.dumps(j)
    with open(inheritRecordFilePath,'w') as f:
        f.write(jstr)

def getInheritFilePath(name,outPath):
    name=name.removeprefix("cv2.")
    name=name.replace(".","/")
    return os.path.normpath(os.path.join(outPath,name))

def cvtPathtoPyimport(key,classname):
    if key==".":
        return f"from . import {classname}"
    elif set(list(key))==set(['/','.']) or key=="..":
        count=key.count("..")+1
        return f"from {'.'*count} import {classname}"
    else:
        print(f"warning: need add new cvtPathtoPyimport rules bacuse:  noknown key:{key} classname:{classname}")

def insertText(filePath,index,text):
    content=""
    TryCreateFile(filePath)
    with open(filePath) as f:
        content=f.read()
    with open(filePath,"w") as f:
        if index<len(content):
            f.write(content[:index]+text+content[index:])
        else:
            f.write(content+text)

def writeInherit(outPath):
    with open(inheritRecordFilePath) as f:
        j=json.loads(f.read())

    for filePath in j:
        
        with open(filePath) as f:
            index=f.read().find('\nT0=typing.TypeVar("T0")\n')+1
        
        for i in j[filePath]:
            targetPath=""
            if i == "cv2":
                targetPath=outPath
            else:
                targetPath=getInheritFilePath(i,outPath)
                if os.path.samefile(targetPath+".pyi",filePath):
                    continue

            filePath=os.path.normpath(filePath)
            fdir=os.path.dirname(filePath)
            relp=os.path.relpath(targetPath,fdir)
            if relp=="." and filePath==os.path.join(outPath,"__init__.pyi"):
                continue
            Pyimport=cvtPathtoPyimport(relp,j[filePath][i])+"\n"
            PyimportLen=len(Pyimport)
            insertText(filePath,index,Pyimport)
            index+=PyimportLen

        insertText(filePath,index,'\n')

def getMostSimilar(child,params,infos):
    paramsAndret=params+[i.strip() for i in child["ret"].split(",")]
    maxSimilarNum=0
    minNoSimilarNum=math.inf
    maxSimilarinfol=[]
    minNoSimilarinfol=[]
    isvoidFuncs=[]
    for info in infos:
        similarNum=0
        nosimilarNum=0
        for CXXparam in info["argInfo"]:
            if CXXparam in paramsAndret:
                similarNum+=1
            else:
                nosimilarNum+=1

        if similarNum>maxSimilarNum:
            maxSimilarNum=similarNum
            maxSimilarinfol=[info]
        elif similarNum==maxSimilarNum:
            maxSimilarinfol.append(info)

        if nosimilarNum<minNoSimilarNum:
            minNoSimilarNum=nosimilarNum
            minNoSimilarinfol=[info]
        elif nosimilarNum==minNoSimilarNum:
            minNoSimilarinfol.append(info)

        if info["retType"]=="void":
            isvoidFuncs.append(info)

    if len(maxSimilarinfol)==1:
        return maxSimilarinfol[0]
    if child["ret"]=="None" and len(isvoidFuncs)==1:
        return isvoidFuncs[0]

    if len(minNoSimilarinfol)==1:
        return minNoSimilarinfol[0]

    overlap= [i for i in maxSimilarinfol if i in minNoSimilarinfol]
    if len(overlap)!=0:
        return overlap[0]
    return maxSimilarinfol[0]

def getFuncInfo(child,params,xmlDirPath):
    infos=getFuncInfos(child["cppname"],xmlDirPath)
    params=[i.rstrip("=...") for i in params]
    if len(infos)==1:
        return infos[0]
    if len(infos)==0:
        return {}
    return getMostSimilar(child,params,infos)

def getIndexFromlist(l,item):
    for i,v in enumerate(l):
        if item==v:
            return i
    return -1

def getHasHint(child,strTAB,xmlDirPath):
    global Krettypes
    pysign=cvtJsonToPy(child)
    params=pysign[pysign.find("(")+1:pysign.rfind(")")].split(",")
    params=[i.strip() for i in params]
    returnTypes=child["ret"].split(",")
    returnTypes=[i.strip() for i in returnTypes]
    pyFuncName=pysign[pysign.find(' ')+1:pysign.rfind('(')]
    info=getFuncInfo(child,params,xmlDirPath)
    oneTAB=' '*4
    Tcount=0

    if info=={}:
        finallyParams=[]
        # 添加泛型的返回类型提示
        for param in params:
            paramName=param
            index=param.find('=')
            hint=""
            if index!=-1:
                paramName=param[:index]
            if paramName in returnTypes:
                hint=f":T{Tcount}"
                paramIndex=getIndexFromlist(returnTypes,paramName)
                returnTypes[paramIndex]=f"T{Tcount}"
                Tcount+=1
            if index!=-1:
                hint+=param[index:]
            finallyParams.append(paramName+hint)
        returnHint=','.join(returnTypes)
        if len(returnTypes)>1:
            returnHint="tuple["+returnHint+"]"
        return strTAB+f"def {pyFuncName}({','.join(finallyParams)}) -> {returnHint}: ..."

    # 获取参数类型提示
    finallyParams=[]

    for param in params:
        paramName=param
        index=param.find('=')
        hint=""
        paramType="typing.Any"
        if index!=-1:
            paramName=param[:index]

        if paramName in info["argInfo"]:
            paramType=info["argInfo"][paramName]["type"]
            paramType=cvtCXXToPYtype(paramType)

        if paramType=="typing.Any":
            if paramName in returnTypes:
                # 添加泛型的返回类型提示
                hint=f":T{Tcount}"
                paramIndex=getIndexFromlist(returnTypes,paramName)
                returnTypes[paramIndex]=f"T{Tcount}"
        else:
            hint=":"+paramType

        if index!=-1:
            hint+=param[index:]
        
        finallyParams.append(f"{paramName}{hint}")

    # 有的参数在py中被作为返回
    for aarg in info["argInfo"]:
        if (aarg in returnTypes) and (aarg not in params):
            Krettypes[aarg]=info["argInfo"][aarg]["type"]
    
    # 获取函数文档
    strTAB2=strTAB+oneTAB
    infodoc=info["doc"]
    if infodoc!="":
        infodoc="```\n"+infodoc+"\n```\n"

    FuncDoc=strTAB2+infodoc
    paramHasDoc=False
    for paramName in info["argInfo"]:
        if info['argInfo'][paramName]['doc']!="":
            paramHasDoc=True
            FuncDoc+="---\n```\nParameters:\n"
            break

    alignLen=28
    if paramHasDoc:
        paramLens=[len(i) for i in info["argInfo"]]
        maxlen=max(paramLens)
        alignLen=max(maxlen,28)
    for paramName in info["argInfo"]:
        if info['argInfo'][paramName]['doc']=="":
            continue
        paramName2=paramName+':'
        FuncDoc+=f"{paramName2:<{alignLen}}{info['argInfo'][paramName]['doc']}\n"

    if paramHasDoc:
        FuncDoc+="```\n"

    FuncDoc=FuncDoc.replace('\n','\n'+strTAB2)
    FuncDoc=strTAB2+'"""\n'+FuncDoc+'"""'

    if FuncDoc.replace("\n","").replace(" ","").replace('`',"").strip() == '""""""':
        FuncDoc=strTAB2+'""""""'

    returnHint=','.join(returnTypes)
    if len(returnTypes)>1:
        returnHint="tuple["+returnHint+"]"
    
    finallyFuncSign=f"def {pyFuncName}({','.join(finallyParams)}) -> {returnHint}:"
    if info["static"]:
        finallyFuncSign="@staticmethod\n"+strTAB+finallyFuncSign
    if child["overload"]:
        finallyFuncSign="@overload\n"+strTAB+finallyFuncSign

    retstr=f"{strTAB}{finallyFuncSign}\n{FuncDoc}"
    return retstr

def removeFileStr(filePath,startIndex,endIndex):
    """
    会删除startIndex与endIndex位置的字符以及其之间的所有字符
    """
    with open(filePath) as f:
        content=f.read()
    content=content[:startIndex]+content[endIndex+1:]
    with open(filePath,"w") as f:
        f.write(content)

def writeFunc(child,filePath,classl):
    strTAB=""
    if classl!=[]:
        strTAB=' '*4*len(classl)
        insertIndex=0
        
        with open(filePath) as f:
            content=f.read()
            insertIndex=0
            for tclassName in classl:
                insertIndex=content.find(f"class {tclassName}",insertIndex)
            insertIndex=insertIndex+1+content[insertIndex+1:].find('\n')
            elipIndex=content.rfind(" ...",insertIndex-5,insertIndex)
        if elipIndex!=-1:
            removeFileStr(filePath,elipIndex,elipIndex+3)
            insertIndex-=4
        text=getHasHint(child,strTAB,TxmlDirPath)
        index=text.find("(")+1
        if "@staticmethod" not in text and index!=text.find(")"):
            text=text[:index]+"self,"+text[index:]
        elif "@staticmethod" not in text:
            text=text[:index]+"self"+text[index:]
        insertText(filePath,insertIndex+1,f"{text}\n\n")
    else:
        TryCreateFile(filePath)
        with open(filePath,"a") as f:
            f.write(f"{getHasHint(child,strTAB,TxmlDirPath)}\n\n")

def writeClassOrFunc(outPath,child,classl):
    if child["filePath"]=="..pyi":
        child["filePath"]="root.pyi"
    filePath=os.path.join(outPath,child["filePath"])
    TryCreateFile(filePath)

    if child["type"]=="class":
        writeclass(child,filePath)
    else:
        writeFunc(child,filePath,classl)

def getConstType(name):
    obj=getFinallyObj(name)
    if type(obj)==type(1):
        return "int"
    else:
        print("warning: noknown "+name)

def writeConst(outPath,child,key):
    if child["filePath"]=="..pyi":
        child["filePath"]="root.pyi"

    filePath=os.path.join(outPath,child["filePath"])
    TryCreateFile(filePath)
    with open(filePath,"a") as f:
        f.write(f"{key}:{getConstType(child['name'])} = ...\n")

def handleLeaf(leaf,outPath,key):
    if leaf["type"] in ["func","class"]:
        writeClassOrFunc(outPath,leaf,leaf["classl"])
    elif leaf["type"] in [type(1)]:
        writeConst(outPath,leaf,key)
    elif leaf["type"] != "module":
        print(f"noknow {key}:\n {leaf} ")

def getFilrPathAndClasss(node):
    classl=[]
    filePath="."
    nodeli=node["name"].split('.')
    fname=""
    cppnames=node["cppname"].split("::")
    if len(cppnames)>2 and cppnames[-1]==cppnames[-2] and getType(node["name"])=="class":
        nodeli.append("__init__")

    for i in nodeli[:-1]:
        fname+="."+i
        itype=getType(fname[1:])
        if itype=="module":
            filePath=os.path.join(filePath,i)
        elif itype == "class":
            classl.append(i)
        elif itype not in [type(1)]:
            print(f"noknown type: {i}:{itype} {node}")
    if filePath==".":
        filePath="__init__"
    filePath+=".pyi"
    return filePath,classl

def organise_pyi(targetPath):
    for root,dirs,files in os.walk(targetPath):
        now_dir_name=os.path.basename(root)
        if "__init__.pyi" not in files:
            srcPath =os.path.join(root,f"../{now_dir_name}.pyi")
            if not os.path.exists(srcPath):
                continue
            destPath=os.path.join(root,"__init__.pyi")
            shutil.move(srcPath,destPath)

        initFilePath=os.path.join(root,"__init__.pyi")
        with open(initFilePath,"a") as f:
            for name in os.listdir(root):
                if "__init__.pyi"==name:
                    continue
                if name.endswith(".pyi"):
                    name=name[:-4]

                f.write(f"\nfrom . import {name}")
 

def handlen(node,outPath):
    handleLeaf(node,outPath,node["name"].split('.')[-1])

def swapn(newdclass,n1,n2):
    newdclass2=newdclass
    v1=newdclass[n1]
    v2=newdclass[n2]
    newdclass2[n1]=v2
    newdclass2[n2]=v1
    return newdclass2

def findclassIndex(newdclass,name):
    name2='.'+name
    for i,item in enumerate(newdclass):
        itemname=item["name"]
        if itemname==name or itemname.endswith(name2):
            return i

def sortclass(newdclass):
    newdclass2=newdclass
    neednext=True
    while neednext:
        neednext=False
        for n in range(len(newdclass2)):
            l={"classl":-1,"baseClassl":-1}
            if newdclass2[n]["classl"]!=[]:
                l["classl"]=n
            if newdclass2[n]["baseClassl"]!=[]:
                l["baseClassl"]=n
            
            for key in l:
                if l[key]==-1:
                    continue
                for classname in newdclass2[l[key]][key]:
                    index=findclassIndex(newdclass2,classname)
                    if index<n:
                        continue
                    newdclass2=swapn(newdclass2,index,n)
                    neednext=True
                    break

    return newdclass2

def sortnewd(newd):
    newdconst=[]
    newdclass=[]
    newdfunc =[]
    for i in newd:
        if "value" in i:
            newdconst.append(i)
        elif "ret" in i:
            newdfunc.append(i)
        else:
            newdclass.append(i)

    newdclass=sortclass(newdclass)
    return newdconst + newdclass + newdfunc

def removeDup(newd):
    newd2=[]
    for i in newd:
        if i not in newd2:
            newd2.append(i)
    return newd2

def getretType2(CXXtype,CXXtypesFile="CXXtypes.json"):
    CXXtypestr=CXXtype.removeprefix("const").rstrip("*").rstrip("&").strip()
    with open(CXXtypesFile) as f:
        CXXtypesTopylist=json.loads(f.read())
    for key in CXXtypesTopylist:
        for v in CXXtypesTopylist[key]:
            index=CXXtypestr.find(v)
            if index!=-1 and (not (((index!=0 and re.match("[a-zA-Z_0-9]",CXXtypestr[index-1])) or (index+len(v)<len(CXXtypestr) and re.match("[a-zA-Z_0-9]",CXXtypestr[index+len(v)]))))):
                CXXtypestr=CXXtypestr.replace(v,key)

    if "std::vector" in CXXtypestr and "<" in CXXtypestr and ">":
        CXXtypestr=CXXtypestr.replace("std::vector","Sequence").replace('<','[').replace('>',']')
        return CXXtypestr
    try:
        obj=getFinallyObj("typing."+CXXtypestr)
        return str(obj)
    except:
        return "typing.Any"

def isclassFromxml(name):
    root=indexxmlRoot
    l1=[i for i in root.xpath(f"compound/name[contains(text(),'::{name}')]") if i.text and i.text.endswith("::"+name)]
    if len(l1)>0:
        return True
    return False
 

def addNoknownType(outPath):
    warnings.filterwarnings("ignore", category=SyntaxWarning)
    for root,_,files in os.walk(outPath):
        for file in files:
            output=io.StringIO()
            reporter=Reporter(output,output)
            if not file.endswith(".pyi"):
                continue

            checkPath(os.path.join(root,file),reporter)
            noknownTypel=[]
            for line in output.getvalue().split('\n'):
                if not ": undefined name '" in line:
                    continue
                line=line[line.find(" name "):]
                noknownTypel.append(re.findall(r"'([a-zA-Z_0-9]+)'",line)[0])
            
            noknownTypel=list(set(noknownTypel))
            f=open(os.path.join(root,file),'a')
            f.write("\n")
            for i in noknownTypel:
                if i=="Mat":
                    relp=os.path.relpath(outPath,root)
                    text=cvtPathtoPyimport(relp,i)
                elif i=="matches_info":
                    text=f"{i}=MatchesInfo"
                elif i in Krettypes:
                    t=cvtCXXToPYtype(Krettypes[i])
                    if t=="typing.Any":
                        t=getretType2(Krettypes[i])
                    if t=="typing.Any" and isclassFromxml(i[0].upper()+i[1:],TxmlDirPath):
                        t=i[0].upper()+i[1:]

                    text=f"{i}={t}"
                else:
                    text=f"{i}=typing.Any"
                
                if "cv::RotatedRect" in text:
                    relp=os.path.relpath(outPath,root)
                    if not (relp=="." and os.path.samefile(os.path.join(root,file),os.path.join(outPath,"__init__.pyi"))):
                        text=text.replace("cv::","")
                        Pyimport=cvtPathtoPyimport(relp,"RotatedRect")+"\n"
                        text=Pyimport+text


                f.write(f"\n{text}")

def findchilds(name,newd):
    childs=[]
    for i in newd:
        if i["name"]==name:
            childs.append(i)
    return childs

def getBaseClasss(classname):
    finobjs=getFinallyObj(classname).__bases__

    if (len(finobjs)==1 and finobjs[0]!=object) or (len(finobjs)>1):
        finobjNames=[i.__name__ for i in finobjs]
        return finobjNames
    return []

def addMoreInfoTonewd(newd):
    newd2=newd
    for n in range(len(newd)):
        node=newd2[n]
        filePath,classl=getFilrPathAndClasss(node)
        ntype=getType(node["name"])
        node["type"]=ntype
        node["filePath"]=filePath
        node["classl"]=classl
        cppnames=node["cppname"].split("::")
        if len(cppnames)>2 and cppnames[-1]==cppnames[-2]:
            node["name"]+=".__init__"
            node["type"] ="func"
            node["ret"]  ="None"

        if len(findchilds(node["name"],newd))>1:
            node["overload"]=True
        else:
            node["overload"]=False
        if node["type"]=="class":
            baseClassl=getBaseClasss(node["name"])
            node["baseClassl"]=baseClassl
        newd2[n]=node

    return newd2

def applyPatch(newd):
    newd2=[]
    patchPath=os.path.join(scriptDIR,"patch.json")
    with open(patchPath) as f:
        j=json.loads(f.read())
    for i in newd:
        childs=findchilds(i["name"],j)
        retChild=i
        if childs!=[]:
            retChild=retChild|childs[0]
        newd2.append(retChild)

    return newd2

def main():
    global TxmlDirPath,indexxmlRoot
    rootPath = sys.argv[1]
    outPath = sys.argv[2]
    cv2_stubsPath=os.path.join(outPath,"cv2")
    TxmlDirPath=os.path.join(rootPath,"doc/doxygen/xml")
    tree=etree.parse(os.path.join(TxmlDirPath,"index.xml"))
    indexxmlRoot=tree.getroot()
 
    open(inheritRecordFilePath,"w").close()
    print("Organising input ...")
    newd = getPySignList(rootPath)
    newd = removeDup(newd)
    newd = addMoreInfoTonewd(newd)
    newd = sortnewd(newd)
    newd = applyPatch(newd)
    
    print("All sorted!\nstart write file...\nThis part of the time may be a bit long, please be patient...")
    for i in newd:
        handlen(i,cv2_stubsPath)
    writeInherit(cv2_stubsPath)
    organise_pyi(cv2_stubsPath)
    addNoknownType(cv2_stubsPath)
    open(os.path.join(cv2_stubsPath,"py.typed"),"w").close()
    os.remove(inheritRecordFilePath)
    print("All stubs have been generated!")

if __name__ == "__main__":
    main()
