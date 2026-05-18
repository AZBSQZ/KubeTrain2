import{_ as Se,g as G,j as Re,o as k,c as Q,a as n,b as l,w as t,J as P,d,h as m,B as Fe,f as s,C as je,k as S,t as R,e as De,q as F,X as Z,F as Ee,r as $e,Y as Ae,p as ee,D as Le,z as Me,H as Oe,E as b,v as le}from"./index-DyRwiSE4.js";const He={class:"algo-list-page"},Je={class:"page-header"},Be={class:"card-header"},Ne={class:"search-form"},Ie={class:"tip-banner"},Xe={class:"tip-row"},Ye={class:"params-define"},qe={class:"params-tip"},Ke={class:"params-warn"},We={class:"template-preview"},Ge={class:"template-header"},Qe={style:{display:"flex",gap:"8px"}},Ze=["innerHTML"],j=`#!/usr/bin/env python3
"""训练脚本模板

系统环境变量（Docker 容器内自动注入）：
  DATASET_PATH  - 数据集目录  (容器内: /data/dataset)
  OUTPUT_PATH   - 输出目录    (容器内: /data/output)
  训练参数通过 config.json 传入，包含 epochs/batch_size/learning_rate 等
"""
import os
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset


def load_config():
    """加载训练配置（系统自动生成 config.json）"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
    return {
        'epochs': int(config.get('epochs', 10)),
        'batch_size': int(config.get('batch_size', 32)),
        'learning_rate': float(config.get('learning_rate', 0.001)),
        'dataset_path': config.get('dataset_path', os.environ.get('DATASET_PATH', '/data/dataset')),
        'output_path': config.get('output_path', os.environ.get('OUTPUT_PATH', '/data/output')),
    }


class SimpleModel(nn.Module):
    """示例模型 - 请替换为实际模型"""
    def __init__(self, input_dim=784, num_classes=10):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, num_classes)
        )

    def forward(self, x):
        return self.fc(x.view(x.size(0), -1))


def main():
    config = load_config()
    print(f"Config: epochs={config['epochs']}, batch_size={config['batch_size']}, lr={config['learning_rate']}")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # === 请在此处加载您的数据集 ===
    X = torch.randn(1000, 784)
    y = torch.randint(0, 10, (1000,))
    loader = DataLoader(TensorDataset(X, y), batch_size=config['batch_size'], shuffle=True)

    model = SimpleModel().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=config['learning_rate'])

    for epoch in range(1, config['epochs'] + 1):
        model.train()
        total_loss, correct, total = 0, 0, 0
        for batch_x, batch_y in loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad()
            output = model(batch_x)
            loss = criterion(output, batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * batch_x.size(0)
            correct += (output.argmax(1) == batch_y).sum().item()
            total += batch_x.size(0)
        avg_loss = total_loss / total
        accuracy = correct / total
        # ===== 关键：输出训练指标（平台通过此行采集数据）=====
        print(f"[METRIC] epoch={epoch}, loss={avg_loss:.4f}, accuracy={accuracy:.4f}")

    os.makedirs(config['output_path'], exist_ok=True)
    torch.save(model.state_dict(), os.path.join(config['output_path'], 'model.pth'))
    print("Training complete.")


if __name__ == '__main__':
    main()
`,el={__name:"Index",setup(ll){const D=m(!1),E=m([]),H=m(0),$=m(1),A=m(12),L=m(""),U=m(""),x=m(!1),T=m(!1),M=m(!1),w=m(!1),J=m(),B=m(),ae=m(),V=m("file"),z=m(null),N=[{name:"epochs",label:"训练轮数",type:"int",default_value:"10"},{name:"batch_size",label:"批次大小",type:"int",default_value:"32"},{name:"learning_rate",label:"学习率",type:"float",default_value:"0.001"}],r=G({name:"",algorithm_type:"",description:"",script_content:"",params:JSON.parse(JSON.stringify(N))}),u=G({id:null,name:"",framework:"PyTorch",task_type:"other",description:"",is_public:!1}),te={name:[{required:!0,message:"算法名称不能为空",trigger:"blur"}]},oe={name:[{required:!0,message:"名称不能为空",trigger:"blur"}]},I=m([]),ne=le(()=>{const o=["classification","regression","clustering","deep_learning"];return[...new Set([...o,...I.value])].filter(Boolean)}),se=le(()=>{const o=e=>e.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");return j.split(`
`).map(e=>{const i=o(e);return e.includes("[METRIC]")||e.includes("METRICS:")?`<span class="hl-key">${i}</span>`:e.includes("# ===== 关键")||e.includes("# 打印配置")?`<span class="hl-comment">${i}</span>`:/^\s*#/.test(e)?`<span class="hl-dim">${i}</span>`:i}).join(`
`)}),ie={image_classification:"图像分类",object_detection:"目标检测",text_classification:"文本分类",language_model:"语言模型",other:"其他"};function de(o){return ie[o]||o||"其他"}function re(o){return o?Me(o).format("YYYY-MM-DD HH:mm"):"-"}async function h(){D.value=!0;try{const o={page:$.value,per_page:A.value,search:L.value};U.value&&(o.framework=U.value);const e=await P.list(o);E.value=e.data.data.items,H.value=e.data.data.total;const i=E.value.map(v=>v.algorithm_type).filter(Boolean);I.value=[...new Set(i)]}finally{D.value=!1}}function ue(){r.params.push({name:"",label:"",type:"float",default_value:""})}function pe(o){r.params.splice(o,1)}function me(o){z.value=o.raw,!r.name&&o.name&&(r.name=o.name.replace(".py",""))}function ce(){z.value=null}function X(){const o=new Blob([j],{type:"text/x-python"}),e=URL.createObjectURL(o),i=document.createElement("a");i.href=e,i.download="algorithm_template.py",i.click(),URL.revokeObjectURL(e),b.success("模板文件已下载")}function fe(){navigator.clipboard.writeText(j).then(()=>{b.success("模板代码已复制到剪贴板")}).catch(()=>{b.error("复制失败，请手动复制")})}function _e(){Object.assign(r,{name:"",algorithm_type:"",description:"",script_content:j,params:JSON.parse(JSON.stringify(N))}),V.value="file",z.value=null,x.value=!0}async function ge(){var o,e;if(await J.value.validate(),V.value==="file"&&!z.value){b.warning("请选择要上传的脚本文件");return}if(V.value==="code"&&!r.script_content){b.warning("请输入脚本内容");return}w.value=!0;try{const i=new FormData;i.append("name",r.name),i.append("algorithm_type",r.algorithm_type),i.append("description",r.description),V.value==="file"?i.append("file",z.value):i.append("script_content",r.script_content);const v=r.params.filter(y=>y.name.trim());v.length>0&&i.append("parameters",JSON.stringify(v));const p=await P.createWithScript(i);p.data.code===200?(b.success("上传成功"),x.value=!1,h()):b.error(p.data.message||"创建失败")}catch(i){b.error(((e=(o=i==null?void 0:i.response)==null?void 0:o.data)==null?void 0:e.message)||"创建失败")}finally{w.value=!1}}function ve(o){Object.assign(u,{id:o.id,name:o.name,framework:o.framework||"PyTorch",task_type:o.task_type||"other",description:o.description||"",is_public:!!o.is_public}),T.value=!0}async function ye(){await B.value.validate(),w.value=!0;try{await P.update(u.id,{name:u.name,framework:u.framework,task_type:u.task_type,description:u.description,is_public:u.is_public}),b.success("更新成功"),T.value=!1,h()}finally{w.value=!1}}async function be(o){await Oe.confirm(`确认删除算法 "${o.name}"？`,"删除确认",{type:"warning"}),await P.delete(o.id),b.success("删除成功"),h()}return Re(h),(o,e)=>{const i=d("plus"),v=d("el-icon"),p=d("el-button"),y=d("el-input"),c=d("el-option"),C=d("el-select"),he=d("el-link"),_=d("el-table-column"),Ve=d("el-tag"),Y=d("el-switch"),q=d("el-table"),we=d("el-pagination"),ke=d("el-card"),xe=d("el-divider"),g=d("el-form-item"),K=d("el-radio"),Te=d("el-radio-group"),ze=d("el-upload"),Ce=d("el-text"),Ue=d("Plus"),W=d("el-form"),O=d("el-dialog"),Pe=Fe("loading");return k(),Q("div",He,[n("div",Je,[e[21]||(e[21]=n("div",{class:"header-info"},[n("h1",null,"算法管理"),n("p",null,"管理训练算法脚本，支持多版本")],-1)),l(p,{type:"primary",onClick:_e},{default:t(()=>[l(v,null,{default:t(()=>[l(i)]),_:1}),e[20]||(e[20]=s(" 上传算法",-1))]),_:1})]),l(ke,{shadow:"never"},{header:t(()=>[n("div",Be,[n("div",Ne,[l(y,{modelValue:L.value,"onUpdate:modelValue":e[0]||(e[0]=a=>L.value=a),placeholder:"搜索算法名称",clearable:"",style:{width:"220px"},"prefix-icon":"Search",onKeyup:De(h,["enter"]),onClear:h},null,8,["modelValue"]),l(C,{modelValue:U.value,"onUpdate:modelValue":e[1]||(e[1]=a=>U.value=a),placeholder:"框架",clearable:"",style:{width:"130px"},onChange:h},{default:t(()=>[l(c,{label:"PyTorch",value:"PyTorch"}),l(c,{label:"TensorFlow",value:"TensorFlow"}),l(c,{label:"JAX",value:"JAX"})]),_:1},8,["modelValue"]),l(p,{type:"primary",onClick:h},{default:t(()=>[...e[22]||(e[22]=[s("搜索",-1)])]),_:1})])])]),default:t(()=>[je((k(),S(q,{data:E.value,stripe:""},{default:t(()=>[l(_,{label:"算法名称",prop:"name","min-width":"160","show-overflow-tooltip":""},{default:t(({row:a})=>[l(he,{type:"primary",onClick:f=>o.$router.push(`/algorithms/${a.id}`)},{default:t(()=>[s(R(a.name),1)]),_:2},1032,["onClick"])]),_:1}),l(_,{label:"框架",width:"100"},{default:t(({row:a})=>[l(Ve,{size:"small",type:"info"},{default:t(()=>[s(R(a.framework),1)]),_:2},1024)]),_:1}),l(_,{label:"任务类型",width:"120"},{default:t(({row:a})=>[s(R(de(a.task_type)),1)]),_:1}),l(_,{label:"版本数",prop:"version_count",width:"80",align:"center"}),l(_,{label:"公开",width:"80",align:"center"},{default:t(({row:a})=>[l(Y,{modelValue:a.is_public,"onUpdate:modelValue":f=>a.is_public=f,size:"small",disabled:""},null,8,["modelValue","onUpdate:modelValue"])]),_:1}),l(_,{label:"创建时间",width:"160"},{default:t(({row:a})=>[s(R(re(a.created_at)),1)]),_:1}),l(_,{label:"操作",width:"180",fixed:"right"},{default:t(({row:a})=>[l(p,{size:"small",onClick:f=>o.$router.push(`/algorithms/${a.id}`)},{default:t(()=>[...e[23]||(e[23]=[s("查看详情",-1)])]),_:1},8,["onClick"]),l(p,{size:"small",onClick:f=>ve(a)},{default:t(()=>[...e[24]||(e[24]=[s("编辑",-1)])]),_:1},8,["onClick"]),l(p,{size:"small",type:"danger",onClick:f=>be(a)},{default:t(()=>[...e[25]||(e[25]=[s("删除",-1)])]),_:1},8,["onClick"])]),_:1})]),_:1},8,["data"])),[[Pe,D.value]]),l(we,{"current-page":$.value,"onUpdate:currentPage":e[2]||(e[2]=a=>$.value=a),"page-size":A.value,"onUpdate:pageSize":e[3]||(e[3]=a=>A.value=a),total:H.value,"page-sizes":[12,20,50],layout:"total, sizes, prev, pager, next",onChange:h,style:{"margin-top":"16px"}},null,8,["current-page","page-size","total"])]),_:1}),l(O,{modelValue:x.value,"onUpdate:modelValue":e[11]||(e[11]=a=>x.value=a),title:"上传算法脚本",width:"700px","destroy-on-close":""},{footer:t(()=>[l(p,{onClick:e[10]||(e[10]=a=>x.value=!1)},{default:t(()=>[...e[38]||(e[38]=[s("取消",-1)])]),_:1}),l(p,{type:"primary",loading:w.value,onClick:ge},{default:t(()=>[...e[39]||(e[39]=[s("确定",-1)])]),_:1},8,["loading"])]),default:t(()=>[n("div",Ie,[n("div",Xe,[l(v,{class:"tip-icon"},{default:t(()=>[l(F(Z))]),_:1}),e[28]||(e[28]=n("span",{class:"tip-text"},"请在训练循环中按以下格式输出指标，否则平台无法展示实时进度和指标曲线。",-1)),l(p,{size:"small",text:"",type:"primary",onClick:e[4]||(e[4]=a=>M.value=!0)},{default:t(()=>[...e[26]||(e[26]=[s("查看规范模板",-1)])]),_:1}),l(xe,{direction:"vertical"}),l(p,{size:"small",text:"",type:"success",onClick:X},{default:t(()=>[...e[27]||(e[27]=[s("下载模板",-1)])]),_:1})]),e[29]||(e[29]=n("div",{class:"tip-code"},[n("span",{class:"tip-code-label"},"推荐格式："),n("code",null,'print("[METRIC] epoch=1, loss=0.5, accuracy=0.8")')],-1))]),l(W,{ref_key:"createFormRef",ref:J,model:r,rules:te,"label-width":"100px"},{default:t(()=>[l(g,{label:"算法名称",prop:"name"},{default:t(()=>[l(y,{modelValue:r.name,"onUpdate:modelValue":e[5]||(e[5]=a=>r.name=a),placeholder:"请输入算法名称"},null,8,["modelValue"])]),_:1}),l(g,{label:"算法类型"},{default:t(()=>[l(C,{modelValue:r.algorithm_type,"onUpdate:modelValue":e[6]||(e[6]=a=>r.algorithm_type=a),placeholder:"可选择或输入自定义类型",style:{width:"100%"},filterable:"","allow-create":"",clearable:"","default-first-option":""},{default:t(()=>[(k(!0),Q(Ee,null,$e(ne.value,a=>(k(),S(c,{key:a,label:a,value:a},null,8,["label","value"]))),128))]),_:1},8,["modelValue"])]),_:1}),l(g,{label:"描述"},{default:t(()=>[l(y,{modelValue:r.description,"onUpdate:modelValue":e[7]||(e[7]=a=>r.description=a),type:"textarea",rows:"2"},null,8,["modelValue"])]),_:1}),l(g,{label:"上传方式"},{default:t(()=>[l(Te,{modelValue:V.value,"onUpdate:modelValue":e[8]||(e[8]=a=>V.value=a)},{default:t(()=>[l(K,{value:"file"},{default:t(()=>[...e[30]||(e[30]=[s("本地文件",-1)])]),_:1}),l(K,{value:"code"},{default:t(()=>[...e[31]||(e[31]=[s("直接输入",-1)])]),_:1})]),_:1},8,["modelValue"])]),_:1}),V.value==="file"?(k(),S(g,{key:0,label:"脚本文件"},{default:t(()=>[l(ze,{ref_key:"uploadRef",ref:ae,"auto-upload":!1,limit:1,"on-change":me,"on-remove":ce,accept:".py",drag:""},{tip:t(()=>[...e[32]||(e[32]=[n("div",{class:"el-upload__tip"},"只支持 .py 文件",-1)])]),default:t(()=>[l(v,{class:"el-icon--upload"},{default:t(()=>[l(F(Ae))]),_:1}),e[33]||(e[33]=n("div",{class:"el-upload__text"},[s("拖拽文件到此处或"),n("em",null,"点击上传")],-1))]),_:1},512)]),_:1})):ee("",!0),V.value==="code"?(k(),S(g,{key:1,label:"脚本内容"},{default:t(()=>[l(y,{modelValue:r.script_content,"onUpdate:modelValue":e[9]||(e[9]=a=>r.script_content=a),type:"textarea",rows:"12",placeholder:"请输入Python脚本代码"},null,8,["modelValue"])]),_:1})):ee("",!0),l(g,{label:"参数定义"},{default:t(()=>[n("div",Ye,[n("div",qe,[l(Ce,{type:"info",size:"small"},{default:t(()=>[l(v,null,{default:t(()=>[l(F(Le))]),_:1}),e[34]||(e[34]=s(" 定义算法支持的训练参数，创建训练任务时必须填写这些参数 ",-1))]),_:1})]),n("div",Ke,[l(v,null,{default:t(()=>[l(F(Z))]),_:1}),e[35]||(e[35]=n("span",null,[n("strong",null,"注意："),s("参数名和默认值必须与脚本中 "),n("code",null,"config.get('参数名', 默认值)"),s(" 完全一致，否则训练时将无法正确传参")],-1))]),l(q,{data:r.params,border:"",size:"small",style:{"margin-top":"8px",width:"100%"}},{default:t(()=>[l(_,{label:"参数名","min-width":"120"},{default:t(({row:a})=>[l(y,{modelValue:a.name,"onUpdate:modelValue":f=>a.name=f,size:"small",placeholder:"参数名（与脚本一致）"},null,8,["modelValue","onUpdate:modelValue"])]),_:1}),l(_,{label:"显示名","min-width":"110"},{default:t(({row:a})=>[l(y,{modelValue:a.label,"onUpdate:modelValue":f=>a.label=f,size:"small",placeholder:"中文名称"},null,8,["modelValue","onUpdate:modelValue"])]),_:1}),l(_,{label:"类型","min-width":"90"},{default:t(({row:a})=>[l(C,{modelValue:a.type,"onUpdate:modelValue":f=>a.type=f,size:"small"},{default:t(()=>[l(c,{label:"整数",value:"int"}),l(c,{label:"小数",value:"float"}),l(c,{label:"字符串",value:"string"})]),_:1},8,["modelValue","onUpdate:modelValue"])]),_:1}),l(_,{label:"默认值","min-width":"100"},{default:t(({row:a})=>[l(y,{modelValue:a.default_value,"onUpdate:modelValue":f=>a.default_value=f,size:"small",placeholder:"默认值"},null,8,["modelValue","onUpdate:modelValue"])]),_:1}),l(_,{label:"操作",width:"60",align:"center"},{default:t(({$index:a})=>[l(p,{type:"danger",size:"small",link:"",onClick:f=>pe(a)},{default:t(()=>[...e[36]||(e[36]=[s("删除",-1)])]),_:1},8,["onClick"])]),_:1})]),_:1},8,["data"]),l(p,{size:"small",type:"primary",link:"",style:{"margin-top":"8px"},onClick:ue},{default:t(()=>[l(v,null,{default:t(()=>[l(Ue)]),_:1}),e[37]||(e[37]=s("添加自定义参数 ",-1))]),_:1})])]),_:1})]),_:1},8,["model"])]),_:1},8,["modelValue"]),l(O,{modelValue:M.value,"onUpdate:modelValue":e[12]||(e[12]=a=>M.value=a),title:"算法脚本模板",width:"900px",top:"5vh","append-to-body":"","destroy-on-close":""},{default:t(()=>[n("div",We,[n("div",Ge,[e[42]||(e[42]=n("span",null,"algorithm_template.py",-1)),n("div",Qe,[l(p,{size:"small",type:"primary",onClick:fe},{default:t(()=>[...e[40]||(e[40]=[s("复制代码",-1)])]),_:1}),l(p,{size:"small",type:"success",onClick:X},{default:t(()=>[...e[41]||(e[41]=[s("下载文件",-1)])]),_:1})])]),n("pre",{class:"template-code",innerHTML:se.value},null,8,Ze)])]),_:1},8,["modelValue"]),l(O,{modelValue:T.value,"onUpdate:modelValue":e[19]||(e[19]=a=>T.value=a),title:"编辑算法",width:"520px","destroy-on-close":""},{footer:t(()=>[l(p,{onClick:e[18]||(e[18]=a=>T.value=!1)},{default:t(()=>[...e[43]||(e[43]=[s("取消",-1)])]),_:1}),l(p,{type:"primary",loading:w.value,onClick:ye},{default:t(()=>[...e[44]||(e[44]=[s("保存",-1)])]),_:1},8,["loading"])]),default:t(()=>[l(W,{ref_key:"editFormRef",ref:B,model:u,rules:oe,"label-width":"90px"},{default:t(()=>[l(g,{label:"名称",prop:"name"},{default:t(()=>[l(y,{modelValue:u.name,"onUpdate:modelValue":e[13]||(e[13]=a=>u.name=a)},null,8,["modelValue"])]),_:1}),l(g,{label:"框架"},{default:t(()=>[l(C,{modelValue:u.framework,"onUpdate:modelValue":e[14]||(e[14]=a=>u.framework=a),style:{width:"100%"}},{default:t(()=>[l(c,{label:"PyTorch",value:"PyTorch"}),l(c,{label:"TensorFlow",value:"TensorFlow"}),l(c,{label:"JAX",value:"JAX"}),l(c,{label:"其他",value:"Other"})]),_:1},8,["modelValue"])]),_:1}),l(g,{label:"任务类型"},{default:t(()=>[l(C,{modelValue:u.task_type,"onUpdate:modelValue":e[15]||(e[15]=a=>u.task_type=a),style:{width:"100%"}},{default:t(()=>[l(c,{label:"图像分类",value:"image_classification"}),l(c,{label:"目标检测",value:"object_detection"}),l(c,{label:"文本分类",value:"text_classification"}),l(c,{label:"语言模型",value:"language_model"}),l(c,{label:"其他",value:"other"})]),_:1},8,["modelValue"])]),_:1}),l(g,{label:"描述"},{default:t(()=>[l(y,{modelValue:u.description,"onUpdate:modelValue":e[16]||(e[16]=a=>u.description=a),type:"textarea",rows:"3"},null,8,["modelValue"])]),_:1}),l(g,{label:"公开"},{default:t(()=>[l(Y,{modelValue:u.is_public,"onUpdate:modelValue":e[17]||(e[17]=a=>u.is_public=a)},null,8,["modelValue"])]),_:1})]),_:1},8,["model"])]),_:1},8,["modelValue"])])}}},tl=Se(el,[["__scopeId","data-v-7521a51b"]]);export{tl as default};
