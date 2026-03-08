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
from lxml import etree # type: ignore
from pyflakes.api import checkPath
from pyflakes.reporter import Reporter

TxmlDirPath="."
scriptDIR=os.path.dirname(os.path.abspath(__file__))
inheritRecordFilePath=f"{time.time()}_{os.getpid()}_inherit.json"
knowTypes={} # 为 getType 函数 缓存

Krettypes={} # 记录参数(这些参数在C++中被作为参数传入,但在py中被作为返回输出)对应的类型,在检查未知返回类型时,会将这些参数定义为正确的类型
indexxmlRoot=None

def getFinallyObj(name,rootModule="cv2"):
    # 将字符串解析为对象例如 "cv.ORB" 返回 cv.ORB
    paths = name.split(".")
    obj = importlib.import_module(rootModule)
    for p in paths:
        obj = getattr(obj, p)
    return obj

def isModule(name):
    try:
        obj=getFinallyObj(name)
        return inspect.ismodule(obj)
    except:
        return False

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

def getType(name):
    # 如果是 "module" "class" "func" 则返回他们的字符串,例如 "cv2" 会返回 "module" 其他类型则直接调用type()返回 例如 "cv2.SORT_EVERY_ROW"会返回 <class 'int'>
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
    # 判断该属性在cv2中是否存在
    paths = name.split(".")
    obj = importlib.import_module("cv2")
    try:
        for p in paths:
            obj = getattr(obj, p)
        return True
    except:
        return False

def finddocfilefromxml(cppname):
    # 根据传入的完全限定名 返回所有符合条件的refid, 即[refid, ....]
    # 该函数只被用于在index.xml寻找对应函数id
    root=indexxmlRoot
    nameIndex=cppname.rfind("::")
    classname=cppname[:nameIndex]
    l1=root.xpath(f"compound/name[text()='{classname}']") # type: ignore
    if len(l1)==1:
        # 正常情况应只有一个对应的字段
        compoundTag=l1[0].getparent()
        targetIDs=[]
        targetName=cppname[nameIndex+2:].replace(" ","")
        # 获取该函数的所有id
        memberNames = compoundTag.xpath(f"member/name[text()='{targetName}']")
        # 函数可能会重载,所以可能会有多个id
        for memberName in memberNames:
            targetIDs.append(memberName.getparent().get("refid"))

        return targetIDs
    elif len(l1)==0:
        return None
    else:
        print("error: match multiple doc!!!!!!!!!")
        return None

def gettypefromCXXtypes(CXXtypesTopylist,CXXtype):
    # CXXtypesTopylist是一个被人工编写的,确定某个c++类型应该转换为对应的py类型的json
    for key in CXXtypesTopylist:
        if CXXtype in CXXtypesTopylist[key]:
            return key
    return None

def cvtCXXToPYtype(CXXtpyestr0,tpyeisAnyListfile=os.path.join(scriptDIR,"CXXtypelist.txt"),CXXtypesFile=os.path.join(scriptDIR,"CXXtypes.json")):
    # 将c++类型转换为py的类型, 缺省值为 "typing.Any"
    
    #  去除在c++类型与py类型对应中可有可无的前缀与后缀,例如: const String  与 String 实际上都是对应py中的str,所以 const 可有可无,去除 const
    CXXtypestr=CXXtpyestr0.removeprefix("const").rstrip("*").rstrip("&").strip()
    
    with open(tpyeisAnyListfile) as f:
        lines=f.readlines()
        tpyeisAnyList=[i.strip() for i in lines]
    with open(CXXtypesFile) as f:
        CXXtypesTopylist=json.loads(f.read())

    t=gettypefromCXXtypes(CXXtypesTopylist,CXXtypestr)
    if t!=None:
        # 已有确定的转换关系则直接返回转换好的py类型
        return t
    elif CXXtpyestr0 in tpyeisAnyList:
        #  tpyeisAnyList 是一个包含一些c++类型的列表,这些类型由于有些复杂,暂时被转换为 py 中的 Any 类型
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
    # 获取函数的id
    refids=finddocfilefromxml(cppname)
    retOverLoad=False

    if refids==None:
        # 没有这个函数的相关文档
        return []
    if len(refids)>1:
        retOverLoad=True

    rets=[] # 函数可能会重载,所以会返回多个文档
    for refid in refids:
        ret={
                "overload":retOverLoad,
                "static":False,
                "argInfo":{}
                }
        # refid包含了该函数文档所在文件的路径,所以直接拼接即可
        targetXmlFilePath=os.path.join(xmlDirPath,refid[:refid.rfind("_")])+".xml"
        try:
            tree=etree.parse(targetXmlFilePath)
        except:
            print(f"File {targetXmlFilePath} parsing error, please check whether you are using doxygen 1.16.1 or a newer version, and delete the generated sutbs.")
        root=tree.getroot()

        memberdefs=root.xpath(f"compounddef/sectiondef/memberdef[@id='{refid}' and @prot='public']")
        if memberdefs==[]:
            continue
        memberdef=memberdefs[0] # refid是唯一的,所以memberdefs 长度应为1 直接使用[0]即可

        # 获取函数返回类型
        retType=''.join(memberdef.xpath("type")[0].itertext())
        ret["retType"]=retType.strip()
        
        # 获取函数是否为静态函数
        if memberdef.get("static")=="yes":
            ret["static"]=True

        # 获取参数的文档与类型
        for param in memberdef.xpath("param"):
            count=0
            # 默认参数名,有些C++函数的签名只有类型,没有参数名,在文档的py部分它们就会被写成 arg{count} 的形式
            paramName=f"arg{count}"
            while paramName in ret["argInfo"]:
                count+=1
                paramName=f"arg{count}"
            
            # 尝试获取对应的参数名
            decnames=param.xpath("declname")
            if decnames!=[]:
                paramName=''.join(decnames[0].itertext())
            # 获取参数类型
            paramType=''.join(param.xpath("type")[0].itertext())
            parameternameTags = memberdef.xpath(f"detaileddescription/para/parameterlist/parameteritem/parameternamelist/parametername[text()='{paramName}']")
            
            # 获取参数文档
            paramDoc=""
            if parameternameTags!=[]:
                paramDocTags=parameternameTags[0].getparent().getparent().xpath("parameterdescription/para")
                if paramDocTags!=[]:
                    paramDoc=''.join(paramDocTags[0].itertext())

            ret["argInfo"][paramName]={"type":paramType,"doc":paramDoc}

        # 获取函数的文档
        doc=""
        briefparaTags=memberdef.xpath("briefdescription/para")
        if briefparaTags!=[]:
            doc=''.join(briefparaTags[0].itertext())
        ret["doc"]=doc

        rets.append(ret)

    return rets


def getPySignList(rootPath):
    # 获取当前py环境存在的cv2的所有类,函数,常量
    # 会重新调整json的布局
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
    # 返回对应的合法py函数定义语句
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
    # 返回对应的合法py类定义语句
    return f"class {jSignDict["name"].split('.')[-1]}"

def cvtConstJsonTopy(jSignDict):
    # 返回对应的合法py常量定义语句
    jtype = getOtherType(jSignDict["name"])
    ret = f"{jSignDict["name"]}:{jtype.__name__}=..."
    return ret


def cvtJsonToPy(jSignDict):
    # 返回对应的py定义语句
    if "ret" in jSignDict:
        return cvtFuncJsonToPy(jSignDict)
    elif "value" in jSignDict:
        return cvtConstJsonTopy(jSignDict)
    else:
        return cvtClassJsonToPy(jSignDict)

def TryCreateFile(filePath):
    # 如果文件不存在则会创建路径上的目录与文件,如果存在,则不会对文件有任何影响
    # 例如: a/b/c.txt 如果a/b/c.txt不存在 a/ b不存在时创建 a/b 目录 a/b/c.txt不存在则创建该文件,并写入base.pyi的内容
    # 写入文件前调用这个函数,以确保文件存在
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
    # 向指定文件写入类定义
    TryCreateFile(filePath)
    l=child["name"].split(".")
    classl=child["classl"]
    insertIndex=0
    strTAB=""
    with open(filePath) as f:
        content=f.read()
    if classl!=[]:
        # classl 是该类的定义被哪些类包含在内,即被哪些类嵌套在其内部(不是基类)
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

    # 获取类的名称
    if l!=[]:
        writeClassStr+=f"class {l[-1]}"
    else:
        writeClassStr+=f"class {child['name']}"

    # 获取基类
    finobjs=getFinallyObj(child["name"]).__bases__
    finobjNames=child["baseClassl"]
    if finobjNames!=[]:
        for i in finobjs:
            recordInherit(filePath,i.__module__,i.__name__)
        writeClassStr+=f"({','.join(finobjNames)})"
    
    # 使用 ... 占位,暂时定为空类
    writeClassStr+=": ...\n"
    insertText(filePath,insertIndex+1,writeClassStr)

def recordInherit(filePath,inherit,classname):
    # 记录这些类的基类
    # 在当前目录生成一个临时的 json 用以记录
    with open(inheritRecordFilePath,"r+") as f:
        content=f.read()
    j={}
    if content!="":
        j=json.loads(content)
    
    filePath=os.path.normpath(filePath)
    if filePath not in j:
        j[filePath]={}

    if inherit not in j[filePath]:
        j[filePath][inherit]=[]

    if classname not in j[filePath][inherit]:
        j[filePath][inherit].append(classname)

    jstr=json.dumps(j)
    with open(inheritRecordFilePath,'w') as f:
        f.write(jstr)

def getInheritFilePath(name,outPath):
    # 获取基类所在文件的路径,如果是 __init__.pyi 则是所在目录的路径
    name=name.removeprefix("cv2.")
    name=name.replace(".","/")
    return os.path.normpath(os.path.join(outPath,name))

def cvtPathtoPyimport(key,classname):
    # 转换为py的import语句
    if key==".":
        return f"from . import {classname}"
    elif set(list(key))==set(['/','.']) or key=="..":
        count=key.count("..")+1
        return f"from {'.'*count} import {classname}"
    else:
        print(f"warning: need add new cvtPathtoPyimport rules bacuse:  noknown key:{key} classname:{classname}")

def insertText(filePath,index,text):
    # 在文件的指定位置插入文本
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
    # 将这些类的基类的import语句写入到文件头部部分
    with open(inheritRecordFilePath) as f:
        j=json.loads(f.read())

    for filePath in j:
        with open(filePath) as f:
            index=f.read().find('\nT0=typing.TypeVar("T0")\n')+1
        
        for i in j[filePath]:
            for ii in j[filePath][i]:
                targetPath=""
                if i == "cv2":
                    targetPath=outPath
                else:
                    targetPath=getInheritFilePath(i,outPath)
                    if os.path.basename(targetPath)!="numpy" and os.path.samefile(targetPath+".pyi",filePath):
                        continue
                if os.path.basename(targetPath)!="numpy":
                    filePath=os.path.normpath(filePath)
                    fdir=os.path.dirname(filePath)
                    relp=os.path.relpath(targetPath,fdir)
                    if relp=="." and filePath==os.path.join(outPath,"__init__.pyi"):
                        continue
                    Pyimport=cvtPathtoPyimport(relp,ii)+"\n" # type: ignore
                else:
                    Pyimport="from numpy import ndarray as numpyndarray\n"
                PyimportLen=len(Pyimport)
                insertText(filePath,index,Pyimport)
                index+=PyimportLen

        insertText(filePath,index,'\n')

def getMostSimilar(child,params,infos):
    # 获取函数文档时,可能有多个,通过这个函数可以获取其中与py中的函数最相符的文档
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
            # 通过参数的名称与数量来计算相似度
            if CXXparam in paramsAndret:
                similarNum+=1
            else:
                nosimilarNum+=1

        # 第一次筛选
        # 更新最相似的 到 maxSimilarinfol
        if similarNum>maxSimilarNum:
            maxSimilarNum=similarNum
            maxSimilarinfol=[info]
        elif similarNum==maxSimilarNum:
            maxSimilarinfol.append(info)
        
        # 第二次筛选,更新不相似列表中,最相似那个
        if nosimilarNum<minNoSimilarNum:
            minNoSimilarNum=nosimilarNum
            minNoSimilarinfol=[info]
        elif nosimilarNum==minNoSimilarNum:
            minNoSimilarinfol.append(info)
        
        # 第三次筛选,如果该py函数返回 None 那么应该对应C++中的 void
        if info["retType"]=="void":
            isvoidFuncs.append(info)

    if len(maxSimilarinfol)==1:
        # 第一次筛选时,已经找到了对应文档
        return maxSimilarinfol[0]
    if child["ret"]=="None" and len(isvoidFuncs)==1:
        # 第三次筛选
        return isvoidFuncs[0]

    if len(minNoSimilarinfol)==1:
        return minNoSimilarinfol[0]
    
    # 通过 第一次与第二次 筛选获得的列表,找出其中重叠的部分
    # 到了这里,如果依旧找到多个最相符的文档,即使人工根据输入查找也无法区分(已在2026.2人工验证)
    overlap= [i for i in maxSimilarinfol if i in minNoSimilarinfol]
    if len(overlap)!=0:
        return overlap[0]
    return maxSimilarinfol[0]

def getFuncInfo(child,params,xmlDirPath):
    # 获取函数文档
    infos=getFuncInfos(child["cppname"],xmlDirPath)
    params=[i.rstrip("=...") for i in params]
    if len(infos)==1:
        return infos[0]
    if len(infos)==0:
        return {}
    return getMostSimilar(child,params,infos)

def getIndexFromlist(l,item):
    # 从一个 list 获取第一个匹配的值的下标
    try:
        return l.index(item)
    except ValueError:
        return -1

def getHasHint(child,strTAB,xmlDirPath):
    # 当函数有文档时,返回包含文档与类型提示的合法py函数定义语句
    # 没有文档则返回不包含文档的合法py函数定义语句(如果有泛型则会包含泛型类型提示)

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
        # 没有文档
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

    # 有的参数在py中被作为返回
    params2=[i.removesuffix("=...") for i in params]
    for aarg in info["argInfo"]:
        if (aarg in returnTypes) and (aarg not in params2):
            counta=1
            aarg2=aarg
            while (aarg2 in Krettypes) and (Krettypes[aarg2]!=info["argInfo"][aarg]["type"]):
                aarg2=f"{aarg}{counta}"
                counta+=1
            Krettypes[aarg2]=info["argInfo"][aarg]["type"]
            returnTypes[getIndexFromlist(returnTypes,aarg)]=aarg2

    # py 签名中,参数部分
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

    # 获取函数文档
    # 格式化文档
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
    
    # 返回的类型提示
    returnHint=','.join(returnTypes)
    if len(returnTypes)>1:
        returnHint="tuple["+returnHint+"]"
    
    finallyFuncSign=f"def {pyFuncName}({','.join(finallyParams)}) -> {returnHint}:"

    # 添加静态函数与重载函数的标记
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
        # 如果该函数在某个类的内部
        strTAB=' '*4*len(classl)
        insertIndex=0
        
        with open(filePath) as f:
            content=f.read()
            # 寻找合适的插入位置
            insertIndex=0
            for tclassName in classl:
                insertIndex=content.find(f"class {tclassName}",insertIndex)
            insertIndex=insertIndex+1+content[insertIndex+1:].find('\n')
            elipIndex=content.rfind(" ...",insertIndex-5,insertIndex)
        if elipIndex!=-1:
            # 该函数所在类因为该函数的插入已经不为空了,所以删除 该类的 ...
            removeFileStr(filePath,elipIndex,elipIndex+3)
            insertIndex-=4
        # 构建插入的函数签名
        text=getHasHint(child,strTAB,TxmlDirPath)
        index=text.find("(")+1
        if "@staticmethod" not in text and index!=text.find(")"):
            text=text[:index]+"self,"+text[index:]
        elif "@staticmethod" not in text:
            text=text[:index]+"self"+text[index:]
        # 插入
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

def getFilePathAndClasss(node):
    # 获取node应该写在哪个文件 应该被哪个类包含在内
    # 因为类有可能是嵌套的,所以classl是列表
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
    # 整理pyi文件
    # 如果存在文件名称(不包含扩展名)与同目录下的一个目录名称相同,则移动到同名目录下,更名为 __init__.pyi
    # 在 __init__.pyi中写入同目录的所有模块的import语句
    for root,_,files in os.walk(targetPath):
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
    # 交换列表中的两个值的位置
    newdclass2=newdclass.copy()
    newdclass2[n1], newdclass2[n2]=newdclass[n2], newdclass[n1]
    return newdclass2

def findclassIndex(newdclass,name):
    # 根据 name 返回下标
    name2='.'+name
    for i,item in enumerate(newdclass):
        itemname=item["name"]
        if itemname==name or itemname.endswith(name2):
            return i

def sortclass(newdclass):
    # 为类的写入顺序进行排序
    newdclass2=newdclass
    neednext=True
    while neednext:
        neednext=False
        for n,item in enumerate(newdclass2):
            l={"classl":-1,"baseClassl":-1}
            if item["classl"]!=[]:
                l["classl"]=n
            if newdclass2[n]["baseClassl"]!=[]:
                l["baseClassl"]=n
            
            for key in l:
                if l[key]==-1:
                    continue
                for classname in newdclass2[l[key]][key]:
                    index=findclassIndex(newdclass2,classname)
                    if index==None:
                        if newdclass2[l[key]][key] == ['ndarray']:
                            newdclass2[l[key]][key]=["numpyndarray"]
                        continue
                    if index<n:
                        continue
                    newdclass2=swapn(newdclass2,index,n)
                    neednext=True
                    break

    return newdclass2

def sortnewd(newd):
    # 排序
    # 常量在最前写入, 然后是类,最后是函数
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
    # 删除列表中的重复项
    newd2=[]
    for i in newd:
        if i not in newd2:
            newd2.append(i)
    return newd2

def getretType2(CXXtype,CXXtypesFile=os.path.join(scriptDIR,"CXXtypes.json")):
    # 将对应的c++函数的返回值转换为py类型
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
    # 通过xml文档判断是否为一个类
    root=indexxmlRoot
    l1=[i for i in root.xpath(f"compound/name[contains(text(),'::{name}')]") if i.text and i.text.endswith("::"+name)] # type: ignore
    if len(l1)>0:
        return True
    return False
 
def getretHasClass(NretType):
    lns=["KeyPoint","cv::RotatedRect","DMatch"]
    for i in lns:
        if i in NretType:
            return i
    return None


def addNoknownType(outPath):
    # 将最后函数返回类型提示中, 未定义的类型进行定义
    warnings.filterwarnings("ignore", category=SyntaxWarning)
    for root,_,files in os.walk(outPath):
        for file in files:
            # 使用检查器,获取文件中未定义的类型
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
            # 处理每个未定义类型
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
                    if t=="typing.Any" and isclassFromxml(i[0].upper()+i[1:]):
                        t=i[0].upper()+i[1:]

                    text=f"{i}={t}"
                else:
                    text=f"{i}=typing.Any"
                
                retHasClass=getretHasClass(text)
                if retHasClass!=None:
                    relp=os.path.relpath(outPath,root)
                    if not (relp=="." and os.path.samefile(os.path.join(root,file),os.path.join(outPath,"__init__.pyi"))):
                        text=text.replace("cv::","") # type: ignore
                        Pyimport=cvtPathtoPyimport(relp,retHasClass.replace("cv::",""))+"\n"
                        text=Pyimport+text
                if "Pose3DPtr" in text:
                    text=text.replace("Pose3DPtr","Pose3D")
                if "numpy.ndarray" in text:
                    text=text.replace("<class 'numpy.ndarray'>","numpyndarray")
                    text="from numpy import ndarray as numpyndarray\n"+text
                text=text.replace("cv::Rect","Rect")
                f.write(f"\n{text}")

def findchilds(name,newd):
    # 根据 name 返回对应的childs
    childs=[]
    for i in newd:
        if i["name"]==name:
            childs.append(i)
    return childs

def getBaseClasss(classname):
    # 获取函数的基类
    finobjs=getFinallyObj(classname).__bases__

    if (len(finobjs)==1 and finobjs[0]!=object) or (len(finobjs)>1):
        finobjNames=[i.__name__ for i in finobjs]
        return finobjNames
    return []

def addMoreInfoTonewd(newd):
    # 为列表中的每个项添加更多的属性
    newd2=newd.copy()
    for n,node in enumerate(newd):
        filePath,classl=getFilePathAndClasss(node)
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
    # 应用补丁
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
    patchPath2=os.path.join(scriptDIR,"patch2.json")
    with open(patchPath2) as f:
        j=json.loads(f.read())

    return newd2+j

def main():
    global TxmlDirPath,indexxmlRoot
    rootPath = sys.argv[1]
    outPath = sys.argv[2]
    cv2_stubsPath=os.path.join(outPath,"cv2")
    TxmlDirPath=os.path.join(rootPath,"doc/doxygen/xml")
    try:
        tree=etree.parse(os.path.join(TxmlDirPath,"index.xml"))
    except:
        print(f"File {os.path.join(TxmlDirPath,"index.xml")} parsing error, please check whether you are using doxygen 1.16.1 or a newer version, and delete the generated sutbs.")
    indexxmlRoot=tree.getroot()
 
    open(inheritRecordFilePath,"w").close()
    print("Organising input ...")
    newd = getPySignList(rootPath)
    newd = applyPatch(newd)
    newd = removeDup(newd)
    newd = addMoreInfoTonewd(newd)
    newd = sortnewd(newd)
    
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
