# -*- coding: utf-8 -*-

import re
import os
import json
import yaml
import pickle
import shutil
import zipfile
import socket
import inspect
import requests
import traceback
import subprocess
import py_compile
import pandas as pd
from tqdm import tqdm
from pathlib import Path
from dramkit.gentools import (isnull,
                              check_list_arg,
                              get_update_kwargs,
                              cut_range_to_subs,
                              get_tmp_col,
                              merge_df,
                              update_df)
from dramkit.logtools.utils_logger import (logger_show,
                                           close_log_file)
from dramkit.datetimetools import timestamp2str
from dramkit.speedup.multi_thread import SingleThread
from dramkit.speedup.multi_process import multi_process_concurrent


def get_input_with_timeout(timeout=10, hint_str=None,
                           logger=None):
    '''
    | 通过input函数获取输入
    | 若等待时间超过timeout秒没接收到输入，则返回None
    | hint_str为input函数提示信息
    | 参考：https://zhuanlan.zhihu.com/p/367634630
    '''
    def _get_input(hint_str):
        str_input = input(hint_str)
        return str_input
    
    if hint_str is None:
        hint_str = 'Please input:\n'

    task = SingleThread(_get_input, (hint_str,), False) # 创建线程
    task.start() # 启动线程
    task.join(timeout=timeout) # 最大执行时间

    # 若超时后，线程依旧运行，则强制结束
    if task.is_alive():
        logger_show('超时未接收到输入，返回None！', logger, 'warn')
        task.stop_thread()

    return task.get_result()


def get_input_multi_line(end_word='end', end_char='',
                         hint_str=None, hint_lineno=True):
    '''
    | input读取多行输入（包括回车换行符也会被保留）
    | end_word设置结束词，当在一行里面输入完整结束词，则表示输入完毕
    | 注：若end_word设置为''，则空行输入回车时会结束输入，
      此时返回结果中上下行之间回车换行符不会被保留
    | end_char设置结束字符串，当在一行里面任意位置输入end_char，则表示输入完毕，
      此时返回在end_char之前输入的内容(不包括end_char和end_char之后的内容)
    | hint_str设置input函数中的输入提示
    | 若hint_lineno为True，则input函数输入时提示当前是第几行
    | 参考：https://blog.csdn.net/weixin_45642669/article/details/114199303
    '''
    if end_word == '\n':
        if end_char == '\n' or end_char == '':
            raise ValueError("`end_word`为`\\n`时`end_char`不能为`\\n`和`''`")
    if hint_str is None:
        hint_str = 'Please input:\n'
    data = end_word
    if hint_lineno:
        lineno = 0
        hint_str_ = str(hint_str)
    while True:
        if hint_lineno:
            lineno += 1
            hint_str = '(第{}行)'.format(lineno) + hint_str_
        var = input(hint_str)
        if var == str(end_word):
            break
        elif end_char != '' and var.find(end_char) != -1:
            var = var[0:var.find(end_char)]
            data = '{}\n{}'.format(data, var)
            break
        else:
            data = '{}\n{}'.format(data, var)
    return data.replace('{}\n'.format(end_word), '')


def pickle_file(data, file):
    '''
    以二进制格式保存数据data到文件file

    Parameters
    ----------
    data :
        待保存内容
    file : str
        保存路径
    '''
    with open(file, 'wb') as f:
        pickle.dump(data, f)


def unpickle_file(file):
    '''
    读取二进制格式文件file

    Parameters
    ----------
    file : str
        待读取文件路径
    '''
    with open(file, 'rb') as f:
        return pickle.load(f)
    
    
def load_yml(fpath, **kwargs_open):
    '''
    | 读取yml文件内容
    | 参考：
    | https://blog.csdn.net/qq_33106045/article/details/108507775
    '''
    with open(fpath, **kwargs_open) as f:
        data = yaml.load(f.read(), Loader=yaml.FullLoader)
    return data
    
    
def write_yml():
    '''写入yml文件'''
    raise NotImplementedError


def load_json(fpath, encoding=None, logger=None):
    '''
    读取json格式文件

    Parameters
    ----------
    fpath : str
        待读取文件路径
    encoding : str, None
        文件编码格式，若不指定，则尝试用utf-8和gbk编码读取
    logger : logging.Logger
        日志记录器


    :returns: `dict` - 返回读取数据
    '''

    if not os.path.exists(fpath):
        logger_show('文件不存在，返回None：{}'.format(fpath),
                    logger, 'warn')
        return None

    try:
        with open(fpath, 'r', encoding=encoding) as f:
            data_json = json.load(f)
    except:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data_json = json.load(f)
        except:
            try:
                with open(fpath, 'r', encoding='gbk') as f:
                    data_json = json.load(f)
            except:
                logger_show('读取%s出错，请检查文件（如编码或文件末尾多余字符等问题）！'%fpath,
                            logger, 'error')
                raise

    return data_json


def write_json(data, fpath, encoding=None, mode='w', **kwargs):
    '''
    把data写入json格式文件

    Parameters
    ----------
    data : dict
        待写入数据
    fpath : str
        文件保存路径
    encoding : str, None
        文件编码格式
    '''
    with open(fpath, mode=mode, encoding=encoding, **kwargs) as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def read_lines(fpath, encoding=None, split=True,
               logger=None, **kwargs_open):
    '''
    读取文本文件中的所有行

    Parameters
    ----------
    fpath : str
        待读取文件路径
    encoding : str, None
        文件编码格式，若不指定，则尝试用utf-8和gbk编码读取
    logger : None, logging.Logger
        日志记录器


    :returns: `list` - 文本文件中每行内容列表
    '''
    try:
        with open(fpath, 'r', encoding=encoding, **kwargs_open) as f:
            lines = f.readlines() if split else f.read()
    except:
        try:
            with open(fpath, 'r', encoding='utf-8', **kwargs_open) as f:
                lines = f.readlines() if split else f.read()
        except:
            try:
                with open(fpath, 'r', encoding='gbk', **kwargs_open) as f:
                    lines = f.readlines() if split else f.read()
            except:
                logger_show('未正确识别文件编码格式，以二进制读取: %s'%fpath,
                            logger, 'warn')
                with open(fpath, 'rb', **kwargs_open) as f:
                    lines = f.readlines() if split else f.read()
    return lines


def write_txt(lines, file, mode='w', check_end=True, **kwargs):
    '''
    将列表lines中的内容写入文本文件中

    Parameters
    ----------
    lines : list
        列表，每个元素为一行文本内容
    file : str
        保存路径
    mode : str
        写入模式，如'w'或'a'
    check_end : bool
        是否检查每行行尾换行符，默认若行尾已经有换行符，则不再新添加换行符
    **kwargs :
        ``open`` 函数接受的关键字，如encoding等

    Note
    ----
    不同系统文本文件每行默认结尾字符不同:

        - linux下一般以`\\\\n`结尾
        - windows下一般以`\\\\r\\\\n`结尾
        - 苹果系统一般以`\\\\r`结尾
    '''
    if check_end:
        lines_ = []
        for x in lines:
            if not (x.endswith('\n') or x.endswith('\r\n') or x.endswith('\r')):
                x = x + '\n'
            lines_.append(x)
    else:
        lines_ = [x+'\n' for x in lines]
    f = open(file, mode=mode, **kwargs)
    f.writelines(lines_)
    f.close()


def load_text(fpath, sep=',', del_first_line=False, del_first_col=False,
              to_pd=True, keep_header=True, encoding=None, del_last_col=False,
              logger=None):
    '''
    读取文本文件数据，要求文件中每行存放一个数据样本

    Parameters
    ----------
    fpath : str
        文本文件路径
    sep : str
        字段分隔符，默认`,`
    del_first_line : bool
        是否删除首行，默认不删除

        .. note:: 若del_first_line为True，则输出pandas.DataFrame没有列名
    del_first_col : bool
        是否删除首列，默认不删除
    to_pd : bool
        是否输出为pandas.DataFrame，默认是
    keep_header : bool
        输出为pandas.DataFrame时是否以首行作为列名，默认是
    encoding : str, None
        指定编码方式，默认不指定时会尝试以uft-8和gbk编码读取
    del_last_col : bool
        是否删除最后一列，默认否
    logger : logging.Logger, None
        日志记录器


    :returns: `list, pandas.DataFrame` - 返回读取的数据
    '''

    if not os.path.exists(fpath):
        logger_show('文件不存在，返回None：%s'%fpath, logger, 'warn')
        return None

    lines = read_lines(fpath, encoding=encoding, logger=logger)

    data = []
    for line in lines:
        line = str(line)
        line = line.strip()
        line = line.split(sep)
        if del_first_col:
            line = line[1:]
        if del_last_col:
            line = line[:-1]
        data.append(line)

    if del_first_line:
        data = data[1:]
        if to_pd:
            data = pd.DataFrame(data)
    else:
        if to_pd:
            if keep_header:
                cols = data[0]
                data = pd.DataFrame(data[1:])
                data.columns = cols
            else:
                data = pd.DataFrame(data)

    return data


def load_csv(fpath, del_unname_cols=True, encoding=None,
             logger=None, **kwargs):
    '''
    用pandas读取csv数据

    Parameters
    ----------
    fpath : str
        csv文件路径
    del_unname_cols : bool
        是否删除未命名列，默认删除
    encoding : str, None
        指定编码方式，默认不指定，不指定时会尝试以uft-8和gbk编码读取
    logger : logging.Logger, None
        日志记录器
    **kwargs :
        其它 ``pd.read_csv`` 支持的参数


    :returns: `pandas.DataFrame` - 读取的数据
    '''

    if not os.path.exists(fpath):
        logger_show('文件不存在，返回None：{}!'.format(fpath),
                    logger, 'warn')
        return None

    try:
        data = pd.read_csv(fpath, encoding=encoding, **kwargs)
    except:
        try:
            data = pd.read_csv(fpath, encoding='utf-8', **kwargs)
        except:
            try:
                data = pd.read_csv(fpath, encoding='gbk', **kwargs)
            except:
                data = pd.read_csv(fpath, **kwargs)

    if del_unname_cols:
        del_cols = [x for x in data.columns if 'Unnamed:' in str(x)]
        if len(del_cols) > 0:
            data.drop(del_cols, axis=1, inplace=True)

    return data


def load_csvs(fpaths,
              kwargs_sort={},
              kwargs_drop_dup={},
              **kwargs_loadcsv):
    '''
    读取指定路径列表中所有的csv文件，整合到一个df里面

    Parameters
    ----------
    fpaths : list
        文件夹路径列表
    kwargs_sort : dict
        设置sort_values接受的排序参数
    kwargs_drop_dup : dict
        设置drop_duplicates接受的去重参数
    **kwargs_loadcsv :
        :func:`dramkit.iotools.load_csv` 接受的其它参数


    :returns: `pandas.DataFrame` - 读取的数据
    '''
    data = []
    for fpath in tqdm(fpaths):
        df = load_csv(fpath, **kwargs_loadcsv)
        data.append(df)
    data = pd.concat(data, axis=0)
    if len(kwargs_sort) > 0:
        _, kwargs_sort = get_update_kwargs('inplace', True, kwargs_sort)
        data.sort_values(**kwargs_sort, inplace=True)
    if len(kwargs_drop_dup) > 0:
        _, kwargs_drop_dup = get_update_kwargs('inplace', True, kwargs_drop_dup)
        data.drop_duplicates(**kwargs_drop_dup, inplace=True)
    return data


def load_csvs_dir(fdir,
                  kwargs_sort={},
                  kwargs_drop_dup={},
                  **kwargs_loadcsv):
    '''
    读取指定文件夹中所有的csv文件，整合到一个df里面

    Parameters
    ----------
    fdir : str
        文件夹路径
    kwargs_sort : dict
        设置sort_values接受的排序参数
    kwargs_drop_dup : dict
        设置drop_duplicates接受的去重参数
    **kwargs_loadcsv :
        :func:`dramkit.iotools.load_csv` 接受的其它参数


    :returns: `pandas.DataFrame` - 读取的数据
    '''
    files = os.listdir(fdir)
    files = [os.path.join(fdir, x) for x in files if x[-4:] == '.csv']
    data = load_csvs(files, kwargs_sort, kwargs_drop_dup,
                     **kwargs_loadcsv)
    return data


def archive_df(df_old, df_new, idcols=None,
               del_dup_cols=None, rep_keep='new',
               sort_cols=None, ascendings=True,
               file_type='.csv', save_path=None,
               kwargs_read={}, kwargs_save={},
               method='merge', logger=None):
    '''
    合并df_new和df_old，再排序、去重、写入csv或excel
    '''
    assert file_type in ['.csv', '.xlsx']
    read_func = load_csv if file_type == '.csv' else pd.read_excel
    if isinstance(df_new, str):
        df_new = read_func(df_new, **kwargs_read)
    if isinstance(df_old, str):
        if os.path.exists(df_old):
            if isnull(df_new) or df_new.shape[0] < 1:
                return df_old
            df_old = read_func(df_old, **kwargs_read)
        else:
            df_old = pd.DataFrame(columns=df_new.columns)
    res = update_df(df_old, df_new,
                    idcols=idcols,
                    del_dup_cols=del_dup_cols,
                    rep_keep=rep_keep,
                    sort_cols=sort_cols,
                    ascendings=ascendings,
                    method=method,
                    logger=logger)
    if not isnull(save_path) and not isnull(res):
        if file_type == '.csv':
            res.to_csv(save_path, **kwargs_save)
        elif file_type == '.xlsx':
            res.to_excel(save_path, **kwargs_save)
    return res


def cut_csv_by_maxline(fpath, max_line=10000,
                       kwargs_loadcsv={},
                       kwargs_tocsv={'index': None}):
    '''
    csv大文件分割，max_line指定子文件最大行数
    '''
    df = load_csv(fpath, **kwargs_loadcsv)
    subs = cut_range_to_subs(df.shape[0], max_line)
    for k in range(len(subs)):
        i0, i1 = subs[k]
        path_ = fpath[:-4]+'_'+str(k+1)+'.csv'
        df_ = df.iloc[i0:i1, :].copy()
        df_.to_csv(path_, **kwargs_tocsv)


def cut_csv_by_year(fpath, tcol=None,
                    name_last_year=False,
                    kwargs_loadcsv={},
                    kwargs_tocsv={'index': None},
                    logger=None):
    '''csv大文件分割，按年份，tcol指定时间列'''
    
    logger_show('数据读取...', logger)
    df = load_csv(fpath, **kwargs_loadcsv)
    if tcol is None:
        for col in ['time', 'date']:
            if col in df.columns:
                tcol = col
                break
    logger_show('年份识别...', logger)
    d_ = get_tmp_col(df, 'date_')
    y_ = get_tmp_col(df, 'year_')
    df[d_] = pd.to_datetime(df[tcol])
    df[y_] = df[d_].apply(lambda x: x.year)
    df[y_] = df[y_].astype(str)
    years = df[y_].unique().tolist()
    years.sort()
    for k in range(len(years)):
        year = years[k]
        logger_show('{}, 数据写入...'.format(year), logger)
        df_ = df[df[y_] == year].copy()
        df_.drop([d_, y_], axis=1, inplace=True)
        path_ = fpath[:-4]+'_'+year+'.csv'
        if k == len(years)-1:
            if not name_last_year:
                path_ = fpath
        df_.to_csv(path_, **kwargs_tocsv)


def load_excels(fdir, kwargs_sort={}, kwargs_drop_dup={},
                **kwargs_readexcel):
    '''
    读取指定文件夹中所有的excel文件，整合到一个df里面

    Parameters
    ----------
    fdir : str
        文件夹路径
    kwargs_sort : dict
        设置sort_values接受的排序参数
    kwargs_drop_dup : dict
        设置drop_duplicates接受的去重参数
    **kwargs_readexcel :
        ``pd.read_excel`` 接受的其它参数


    :returns: `pandas.DataFrame` - 读取的数据
    '''
    files = os.listdir(fdir)
    files = [os.path.join(fdir, x) for x in files if x[-4:] == '.xls' or x[-5:] == '.xlsx']
    data = []
    for file in files:
        df = pd.read_excel(file, **kwargs_readexcel)
        data.append(df)
    data = pd.concat(data, axis=0)
    if len(kwargs_sort) > 0:
        _, kwargs_sort = get_update_kwargs('inplace', True, kwargs_sort)
        data.sort_values(**kwargs_sort, inplace=True)
    if len(kwargs_drop_dup) > 0:
        _, kwargs_drop_dup = get_update_kwargs('inplace', True, kwargs_drop_dup)
        data.drop_duplicates(**kwargs_drop_dup, inplace=True)
    return data


def clear_text_file(fpath, encoding=None):
    '''清空文本文件中的内容，保留文件'''
    with open(fpath, 'w', encoding=encoding) as f:
        f.writelines([''])
        
        
def clear_specified_type_files(dir_path, type_list,
                               encoding=None,
                               recu_sub_dir=False,
                               **kwargs_getpath):
    '''清空dir_path文件夹下所有类型在type_list中的文件内容，保留文件夹'''
    fpaths = get_all_paths(dir_path, ext=type_list,
                           recu_sub_dir=recu_sub_dir,
                           abspath=True, **kwargs_getpath)
    for fpath in fpaths:
        clear_text_file(fpath, encoding=encoding)


def get_all_paths(dir_path, ext=None, start=None,
                  include_dir=False, abspath=False,
                  recu_sub_dir=True, only_dir=False,
                  name_func=None):
    '''
	获取指定文件夹(及其子文件夹)中所有的文件路径

    Parameters
    ----------
    dir_path : str
        文件夹路径
    ext : None, str, list, tuple
        指定文件后缀列表，若为None，则包含所有类型文件
    start : None, str, list, tuple
        指定文件前缀名列表，若为None，则包含所有类型文件
    include_dir : bool
        返回结果中是否包含文件夹路径（包含返回文件路径的文件夹），默认不包含（即只返回文件路径）
    abspath : bool
        是否返回绝对路径，默认返回相对路径
    rec_sub_dir : bool
        若为False，则不对子文件中的文件进行遍历，即只返回dir_path下的文件（夹）路径
    only_dir : bool
        若为True，则只返回子文件夹路径(文件夹名称尾部与ext指定尾部相同的文件夹)，
        不返回文件路径，此时include_dir不起作用
    name_func : function
        判断是否符合文件名筛选的函数，即满足name_func(fpath)值为True的路径被保留，
        name_func参数为路径，返回结果只能为True或False


    :returns: `list` - 文件路径列表
	'''
    if not (ext is None or isinstance(ext, (list, tuple)) or isinstance(ext, str)):
        raise ValueError('`ext`必须为None或str或list,tuple类型！')
    if not (start is None or isinstance(start, (list, tuple)) or isinstance(start, str)):
        raise ValueError('`start`必须为None或str或list,tuple类型！')
    if not ((name_func is None) and (not callable(name_func))):
        raise ValueError('`name_func`必须为None或函数！')
    if ext is not None and isinstance(ext, str):
        ext = [ext]
    if start is not None and isinstance(start, str):
        start = [start]
    def _tokeep(name):
        name_ = os.path.basename(name)
        cond1 = True
        if not isnull(ext):
            # cond1 = any([name_[-len(x):] in ext for x in ext])
            cond1 = any([name_.endswith(x) for x in ext])
        cond2 = True
        if not isnull(start):
            # cond2 = any([name_[:len(x)] in start for x in start])
            cond2 = any([name_.startswith(x) for x in start])
        cond3 = True
        if not isnull(name_func):
            cond3 = name_func(name_)
        if cond1 and cond2 and cond3:
            return True
        return False
    if recu_sub_dir:
        fpaths = []
        for root, dirs, files in os.walk(dir_path):
            if only_dir:
                if _tokeep(root):
                    fpaths.append(root)
            else:
                if include_dir:
                    if _tokeep(root):
                        fpaths.append(root)
                for fname in files:
                    if _tokeep(fname):
                        fpaths.append(os.path.join(root, fname))
                        if include_dir:
                            fpaths.append(root)
    else:
        fpaths = [os.path.join(dir_path, x) for x in os.listdir(dir_path)]
        fpaths = [dir_path] + fpaths
        if only_dir:
            fpaths = [x for x in fpaths if os.path.isdir(x)]
        else:
            if not include_dir:
                fpaths = [x for x in fpaths if not os.path.isdir(x)]
        fpaths = [x for x in fpaths if _tokeep(x)]
    if abspath:
        fpaths = [os.path.abspath(x) for x in fpaths]
    return list(set(fpaths))


def del_specified_type_files(dir_path, type_list, recu_sub_dir=True,
                             **kwargs_getpath):
    '''删除dir_path文件夹下所有类型在type_list中的文件'''
    fpaths = get_all_paths(dir_path, ext=type_list, recu_sub_dir=recu_sub_dir,
                           abspath=True, **kwargs_getpath)
    for fpath in fpaths:
        os.remove(fpath)
    
    
def del_dir(dir_path):
    '''删除dir_path指定文件夹及其所有内容'''
    shutil.rmtree(dir_path)
    
    
def del_specified_subdir(dir_path, del_names, recu_sub_dir=True,
                         **kwargs_getpath):
    '''删除dir_path文件夹下所有文件夹名尾缀在del_names中的子文件夹'''
    subdirs = get_all_paths(dir_path, ext=del_names, only_dir=True,
                            abspath=True, recu_sub_dir=recu_sub_dir,
                            **kwargs_getpath)
    for subdir in subdirs:
        shutil.rmtree(subdir)
    

def copy_file_to_dir(src_path, tgt_dir, force=True):
    '''复制文件'''
    make_dir(tgt_dir)
    if not force:
        tgt_path = os.path.join(tgt_dir,
                                os.path.basename(src_path))
        if os.path.exists(tgt_path):
            return
    if os.path.exists(tgt_dir) and not os.path.isdir(tgt_dir):
        raise ValueError('目标路径不是文件夹，请检查！')
    shutil.copy(src_path, tgt_dir)
    
    
def copy_file_to_file(src_path, tgt_path, force=True):
    '''文件复制（指定文件名）'''
    if not force and os.path.exists(tgt_path):
        return
    shutil.copy(src_path, tgt_path)
    
    
def _get_copy_abs_tgt_dir(src_dir, tgt_dir, keep_root_same):
    abs_dir_path = os.path.abspath(src_dir)
    abs_tgt_dir = os.path.abspath(tgt_dir)
    src_name = os.path.split(abs_dir_path)[-1]
    tgt_name = os.path.split(abs_tgt_dir)[-1]
    if src_name != tgt_name and keep_root_same:
        abs_tgt_dir = os.path.abspath(os.path.join(abs_tgt_dir, src_name))
    return abs_tgt_dir
    
    
def copy_dir_structure(src_dir, tgt_dir,
                       ext=None, recu_sub_dir=True,
                       keep_root_same=True,
                       return_map=False,
                       **kwargs_getpath):
    '''复制文件夹结构，不复制里面的文件'''
    subdirs = get_all_paths(src_dir, ext=ext, only_dir=True,
                            abspath=True, recu_sub_dir=recu_sub_dir,
                            **kwargs_getpath)
    abs_dir_path = os.path.abspath(src_dir)
    abs_tgt_dir = _get_copy_abs_tgt_dir(src_dir, tgt_dir, keep_root_same)
    tgt_dirs = [x.replace(abs_dir_path, abs_tgt_dir) for x in subdirs]
    for tgt in tgt_dirs:
        make_dir(tgt)
    if return_map:
        return dict(zip(subdirs, tgt_dirs))
    return


def copy_dir(src_dir, tgt_dir, ext_file=None, ext_dir=None,
             recu_sub_dir=True, force=True, keep_root_same=True,
             keep_empty_dir_when_not_recu=False,
             kwargs_getpath_dir={}, kwargs_getpath_file={}):
    '''复制整个文件夹及其内容'''
    if not recu_sub_dir and not keep_empty_dir_when_not_recu:
        fpaths = get_all_paths(src_dir, ext=ext_file, include_dir=False,
                               abspath=True, recu_sub_dir=False,
                               only_dir=False, **kwargs_getpath_dir)
        abs_tgt_dir = _get_copy_abs_tgt_dir(src_dir, tgt_dir, keep_root_same)
        for fpath in fpaths:
            copy_file_to_dir(fpath, abs_tgt_dir, force=force)
    else:
        dir_map = copy_dir_structure(src_dir, tgt_dir, ext=ext_dir,
                                     recu_sub_dir=recu_sub_dir,
                                     keep_root_same=keep_root_same,
                                     return_map=True)
        fpaths = get_all_paths(src_dir, ext=ext_file, include_dir=False,
                               abspath=True, recu_sub_dir=recu_sub_dir,
                               only_dir=False, **kwargs_getpath_file)
        for fpath in fpaths:
            tdir = dir_map[os.path.dirname(fpath)]
            copy_file_to_dir(fpath, tdir, force=force)
    
    
def move_file_to_file(src_path, tgt_path, force=True):
    '''移动文件（指定文件名）'''
    if not force and os.path.exists(tgt_path):
        return
    shutil.move(src_path, tgt_path)
    
    
def move_file_to_dir(src_path, tgt_dir, force=True):
    '''移动文件'''
    make_dir(tgt_dir)
    if not force:
        tgt_path = os.path.join(tgt_dir,
                                os.path.basename(src_path))
        if os.path.exists(tgt_path):
            return
    if os.path.exists(tgt_dir) and not os.path.isdir(tgt_dir):
        raise ValueError('目标路径不是文件夹，请检查！')
    shutil.move(src_path, tgt_dir)
    
    
def move_dir(src_dir, tgt_dir, ext_file=None, ext_dir=None,
             recu_sub_dir=True, force=True, keep_root_same=True,
             keep_empty_dir_when_not_recu=False,
             kwargs_getpath_dir={}, kwargs_getpath_file={}):
    '''移动整个文件夹及其内容'''
    if not recu_sub_dir and not keep_empty_dir_when_not_recu:
        fpaths = get_all_paths(src_dir, ext=ext_file, include_dir=False,
                               abspath=True, recu_sub_dir=False,
                               only_dir=False, **kwargs_getpath_dir)
        abs_tgt_dir = _get_copy_abs_tgt_dir(src_dir, tgt_dir, keep_root_same)
        for fpath in fpaths:
            move_file_to_dir(fpath, abs_tgt_dir, force=force)
        if len(os.listdir(src_dir)) == 0:
            os.removedirs(src_dir)
    else:
        dir_map = copy_dir_structure(src_dir, tgt_dir, ext=ext_dir,
                                     recu_sub_dir=recu_sub_dir,
                                     keep_root_same=keep_root_same,
                                     return_map=True)
        fpaths = get_all_paths(src_dir, ext=ext_file, include_dir=False,
                               abspath=True, recu_sub_dir=recu_sub_dir,
                               only_dir=False, **kwargs_getpath_file)
        for fpath in fpaths:
            tdir = dir_map[os.path.dirname(fpath)]
            move_file_to_dir(fpath, tdir, force=force)
        for dir1, dir2 in dir_map.items():
            if len(os.listdir(dir1)) == 0:
                os.removedirs(dir1)
            if len(os.listdir(dir2)) == 0:
                os.removedirs(dir2)
    
    
def move_specified_type_files(dir_path,
                              type_list,
                              target_dir,
                              recu_sub_dir=True):
    '''移动dir_path文件夹下所有类型在type_list中的文件到target_dir中'''
    raise NotImplementedError
    
    
def make_dir(dir_path):
    '''新建文件夹'''
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        
        
def make_path_dir(fpath):
    '''若fpath所指文件夹路径不存在，则新建之'''
    if isnull(fpath):
        return
    dir_path = os.path.dirname(fpath)
    if not os.path.exists(dir_path) and len(dir_path) > 0:
        make_dir(dir_path)
        
        
def get_last_change_time(fpath, strformat='%Y-%m-%d %H:%M:%S'):
    '''获取文件的最后修改时间'''
    return timestamp2str(os.stat(fpath).st_mtime, strformat)


def get_file_info(fpath):
    '''获取文件信息'''
    infos = os.stat(fpath)
    r = {}
    r['size_b'] = infos.st_size # 文件大小，字节
    r['size_kb'] = r['size_b'] / 1024 # 文件大小，KB
    r['size_mb'] = r['size_kb'] / 1024 # 文件大小，MB
    r['size_gb'] = r['size_mb'] / 1024 # 文件大小，GB
    r['modify_time'] = timestamp2str(infos.st_mtime) # 最后修改时间
    return r


def get_files_info(fpaths):
    '''获取列表中的文件信息'''
    infos = []
    for fpath in fpaths:
        info = get_file_info(fpath)
        info['file'] = fpath
        infos.append(info)
    infos = pd.DataFrame(infos)
    infos = infos[['file', 'modify_time', 'size_kb', 'size_mb', 'size_b', 'size_gb']]
    return infos


def get_files_info_dir(dir_path, **kwargs_getpath):
    '''
    | 获取dir_path文件夹中所有文件的信息
    | \**kwargs为 :func:`dramkit.iotoos.get_all_paths` 接受的参数
    '''
    fpaths = get_all_paths(dir_path, **kwargs_getpath)
    return get_files_info(fpaths)
    
    
def py2pyc(py_path, pyc_path=None, force=True, del_py=False,
           **kwargs_compile):
    '''py文件编译为pyc文件'''
    if pyc_path is None:
        pyc_path = py_path + 'c'
    if not force:
        if not os.path.exists(pyc_path):
            py_compile.compile(py_path, pyc_path)
    else:
        if os.path.exists(pyc_path):
            os.remove(pyc_path)
        py_compile.compile(py_path, pyc_path, **kwargs_compile)
    if del_py:
        os.remove(py_path)
    
    
def py2pyc_dir(dir_path, force=True, del_py=False,
               recu_sub_dir=True, kwargs_compile={}, kwargs_getpath={}):
    '''将一个文件夹下的所有.py文件编译为.pyc文件'''
    all_pys = get_all_paths(dir_path, ext='.py', recu_sub_dir=recu_sub_dir,
                            abspath=True, **kwargs_getpath)
    for fpy in all_pys:
        fpyc = fpy+'c'
        py2pyc(fpy, pyc_path=fpyc, force=force,
               del_py=del_py, **kwargs_compile)
        
        
def pyc2py(pyc_path, py_path=None, force=True,
           del_pyc=False, logger=None):
    '''pyc文件反编译为py'''
    def _pyc2py(pyc_path, py_path, logger):
        cmdstr = 'uncompyle6 -o {} {}'.format(py_path, pyc_path)
        try:
            cmdinfo = subprocess.check_output(cmdstr, shell=True,
                                              stderr=subprocess.STDOUT)
        except:
            if os.path.exists(py_path):
                os.remove(py_path)
            logger_show('%s反编译失败: %s'%(pyc_path, traceback.format_exc()),
                        logger, 'error')
            return
        cmdinfo = cmdinfo.decode('gbk')
        cmdinfo = cmdinfo.replace('\r\n', '\n')
        logger_show(cmdinfo, logger, 'info')        
    if py_path is None:
        py_path = pyc_path.replace('.pyc', '.py')
        if 'cpython' in pyc_path:
            tmp = pyc_path.split('.')
            tmp = [x for x in tmp if 'cpython'  in x][0]
            py_path = py_path.replace('.'+tmp, '')
    if not force:
        if not os.path.exists(py_path):
            _pyc2py(pyc_path, py_path, logger)
    else:
        if os.path.exists(py_path):
            os.remove(py_path)
        _pyc2py(pyc_path, py_path, logger)    
    if del_pyc:
        logger_show('remove %s'%pyc_path, logger, 'warn')
        os.remove(pyc_path)
        
        
def pyc2py_dir(dir_path, force=True, del_pyc=False,
               recu_sub_dir=True, logger=None, **kwargs_getpath):
    '''将一个文件夹下的所有.pyc文件反编译为.py文件'''
    all_pycs = get_all_paths(dir_path, ext='.pyc', recu_sub_dir=recu_sub_dir,
                             abspath=True, **kwargs_getpath)
    n = len(all_pycs)
    for k in range(n):
        fpyc = all_pycs[k]
        logger_show('%s / %s ...'%(k+1, n), logger, 'info')
        pyc2py(fpyc, force=force, del_pyc=del_pyc, logger=logger)
            
            
def get_mac_address():
    '''
    获取Mac地址，返回大写地址，如：F8-A2-D6-CC-BB-AA
    '''
    import uuid
    mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
    # 转大写
    mac = '-'.join([mac[e: e+2] for e in range(0, 11, 2)]).upper()
    return mac


def get_hardware_ids():
    '''
    | 获取电脑硬件序列号信息，包括主板和硬盘序列号、MAC地址、BIOS序列号等
    | 参考：https://blog.csdn.net/lekmoon/article/details/111478394
    '''
    import wmi
    results = {'cpu': [],
               'base_board': [],
               'disk': [],
               'network_mac': [],
               'bios': []}
    infos = wmi.WMI()
    # CPU序列号
    for cpu in infos.Win32_Processor():
        id_ = cpu.ProcessorId
        if id_ is not None:
            results['cpu'].append(id_.strip())
    # 主板序列号
    for board in infos.Win32_BaseBoard():
        id_ = board.SerialNumber
        if id_ is not None:
            results['base_board'].append(id_.strip())
    # 硬盘序列号
    for disk in infos.Win32_DiskDrive():
        id_ = disk.SerialNumber
        if id_ is not None:
            results['disk'].append(id_.strip())
    # mac地址
    for mac in infos.Win32_NetworkAdapter():
        id_ = mac.MACAddress
        if id_ is not None:
            results['network_mac'].append(id_.strip().replace(':', '-'))
    # bios序列号    
    for bios in infos.Win32_BIOS():
        id_ = bios.SerialNumber
        if id_ is not None:
            results['bios'].append(id_.strip())
    return results


def get_ip1():
    '''
    | 获取ip地址
    | 参考：https://blog.csdn.net/hemadaili/article/details/89555681
    '''
    return socket.gethostbyname(socket.gethostname())

 
def get_ip2():
    '''
    | 查询ip地址
    | 参考：https://blog.csdn.net/qq_36530891/article/details/102725580
    '''
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close() 
    return ip


def get_ip_public():
    '''
    | 获取公网ip
    | 参考：https://zhuanlan.zhihu.com/p/262185582
    '''
    # 可以获取公网ip的网站
    ip_html = requests.get('http://txt.go.sohu.com/ip/soip')
    # 从响应中提取公网ip
    cur_public_ip = re.findall(r'\d+.\d+.\d+.\d+', ip_html.text)
    return cur_public_ip[0]


def get_tasks_info_win():
    '''windows下获取任务信息'''
    res = cmdrun('tasklist', logger=False)
    res = res.split('\n')[1:-1]
    cols = re.sub(' +', ',', res[0].strip()).split(',')
    lens = [len(x) for x in res[1].split(' ')]
    idxs, start, end = [], 0, 0
    for k in range(len(lens)):
        end = start + lens[k]
        idxs.append([start, end])
        start = start + lens[k] + 1
    del res[1]
    res = [[x.strip()[k1:k2].strip() for k1, k2 in idxs] for x in res]
    res = pd.DataFrame(res[2:], columns=cols)
    return res


def get_ports_info_win():
    '''windows下获取端口信息'''
    res = cmdrun('netstat -ano', logger=False)
    res = res.split('\n')[3:-1]
    res = [re.sub(' +', ',', x.strip()) for x in res] # 替换连续空格
    res = [x.split(',') for x in res]
    res = pd.DataFrame(res[1:], columns=res[0])
    res['端口'] = res['本地地址'].apply(lambda x: x.split(':')[-1])
    res['端口'] = res['端口'].astype(int)
    tasks = get_tasks_info_win()
    res = merge_df(res, tasks, how='left', on='PID')
    return res


def zip_files(zip_path, fpaths, keep_ori_path=True, keep_zip_new=True):
    '''
    使用zipfile将指定路径列表(不包括子文件(夹)内容)打包为.zip文件

    Parameters
    ----------
    zip_path : str
        zip压缩包保存路径
    fpaths : list
        需要压缩的路径列表(应为相对路径)
    keep_ori_path : bool
        - 若为True, 则压缩文件会保留fpaths中文件的原始路径
        - 若为False, 则fpaths中所有文件在压缩文件中都在统一根目录下
    keep_zip_new : bool
        若为True，将覆盖已有压缩文件，否则在已有文件里面新增
    '''
    if keep_zip_new:
        f = zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED)
    else:
        f = zipfile.ZipFile(zip_path, 'a', zipfile.ZIP_DEFLATED)
    if keep_ori_path:
        for fpath in fpaths:
            f.write(fpath)
    else:
        for fpath in fpaths:
            file = os.path.basename(fpath)
            f.write(fpath, file)
    f.close()
    
    
def zip_fpath(fpath, zip_path=None, kwargs_zip={}, kwargs_getpath={}):
    '''
    使用zipfile压缩单个文件(夹)下所有内容为.zip文件

    Parameters
    ----------
    fpath : str
        待压缩文件(夹)路径(应为相对路径)
    zip_path : None, str
        压缩文件保存路径，若为None，则为fpath路径加后缀
    **kwargs_zip :
        :func:`dramkit.iotools.zip_files` 接受的参数
    '''
    if isnull(zip_path):
        if os.path.isdir(fpath) and fpath[-1] == '/':
            zip_path = fpath[:-1] + '.zip'
        else:
            zip_path = fpath + '.zip'
    if os.path.isfile(fpath): # fpath为文件
        zip_files(zip_path, [fpath], **kwargs_zip)
    elif os.path.isdir(fpath): # fpath为文件夹
        fpaths = get_all_paths(fpath, include_dir=True, **kwargs_getpath)
        zip_files(zip_path, fpaths, **kwargs_zip)


def zip_fpaths(zip_path, fpaths, kwargs_zip={}, kwargs_getpath={}):
    '''
    使用zipfile将指定路径列表(包括子文件(夹)所有内容)打包为.zip文件

    Parameters
    ----------
    zip_path : str
        zip压缩包保存路径
    fpaths : list
        需要压缩的路径列表(可为文件也可为文件夹, 应为相对路径)
    **kwargs_zip :
        :func:`dramkit.iotools.zip_files` 接受的参数
    '''
    all_paths = []
    for fpath in fpaths:
        if os.path.isfile(fpath):
            all_paths.append(fpath)
        elif os.path.isdir(fpath):
            all_paths += get_all_paths(fpath, include_dir=True,
                                       **kwargs_getpath)
    zip_files(zip_path, all_paths, **kwargs_zip)


def zip_extract(fzip, to_dir=None, replace_exists=True):
    '''用zipfile解压文件'''
    raise NotImplementedError


def zip_fpath_7z(fpath, zip_path=None, mode='zip', pwd=None, keep_zip_new=True):
    '''
    7z命令压缩单个文件(夹)到.zip文件

    Parameters
    ----------
    fpath : str
        待压缩文件(夹)路径
    zip_path : None, str
        压缩文件保存路径，若为None，则为fpath路径加后缀
    mode : str
        压缩文件后缀，可选['7z', 'zip']
    pwd : str
        密码字符串
    keep_zip_new : bool
        - 若为True，则zip_path将覆盖原来已经存在的文件
        - 若为False，则zip_path将在原来已有的文件中新增需要压缩的文件
    '''

    fpath = os.path.abspath(fpath) # 绝对路径

    if isnull(zip_path):
        if os.path.isdir(fpath) and fpath[-1] == '/':
            zip_path = fpath[:-1] + '.zip'
        else:
            zip_path = fpath + '.zip'
    else:
        zip_path = os.path.abspath(zip_path)

    if os.path.exists(zip_path) and keep_zip_new:
        os.remove(zip_path)

    md_str = ' -t' + mode

    if isnull(pwd):
        pwd = ''
    else:
        pwd = ' -p' + str(pwd)

    cmd_str = '7z a ' + zip_path + ' ' + fpath + md_str + pwd

    # os.system(cmd_str) # windows下会闪现cmd界面
    subprocess.call(cmd_str, shell=True)


def zip_fpaths_7z(zip_path, fpaths, mode='zip', pwd=None, keep_zip_new=True):
    '''
    7z命令压缩多个文件(夹)列表到.zip文件

    Parameters
    ----------
    zip_path : str
        zip压缩包保存路径
    fpaths : list
        待压缩文件(夹)路径列表

        .. warning:: fpaths太长的时候可能会报错
    mode : str
        压缩文件后缀，可选['7z', 'zip']
    pwd : str
        密码字符串
    keep_zip_new : bool
        - 若为True，则zip_path将覆盖原来已经存在的文件
        - 若为False，则zip_path将在原来已有的文件中新增需要压缩的文件
    '''

    md_str = ' -t' + mode

    if isnull(pwd):
        pwd = ''
    else:
        pwd = ' -p' + str(pwd)

    if os.path.exists(zip_path) and keep_zip_new:
        os.remove(zip_path)

    fpaths_str = ' '.join([os.path.abspath(x) for x in fpaths])

    cmd_str = '7z a ' + zip_path + ' ' + fpaths_str + md_str + pwd

    # os.system(cmd_str) # windows下会闪现cmd界面
    subprocess.call(cmd_str, shell=True)


def extract_7z():
    '''7z命令解压文件'''
    raise NotImplementedError


def cmdrun(cmd_str, logger=None):
    '''调用cmd执行cmd_str命令'''
    p = subprocess.Popen(cmd_str,
                         shell=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         encoding='gbk'
                         )
    res = p.communicate()[0]
    logger_show(res, logger)
    return res


def _cmdrun(args):
    return cmdrun(*args)
    
    
def cmdruns_multi_process(cmd_str_list, logger=None,
                          multi_line=None, keep_order=True):
    args_list = [[cmd_str, logger] for cmd_str in cmd_str_list]
    if not keep_order:
        res = multi_process_concurrent(cmdrun, args_list,
                                       multi_line=multi_line,
                                       keep_order=False)
    else:
        res = multi_process_concurrent(_cmdrun, args_list,
                                       multi_line=multi_line,
                                       keep_order=True)
    logger_show('\n'.join(res), logger)
    return res
    
    
def cmd_run_pys_multi_process(py_list, logger=None,
                              multi_line=None, keep_order=True):
    cmd_str_list = ['python %s'%py for py in py_list]
    return cmdruns_multi_process(cmd_str_list, logger=logger,
                                 multi_line=multi_line, keep_order=keep_order)
    
    
def cmd_run_pys(py_list, logger=None):
    '''cmd命令批量运行py脚本，logger捕捉日志'''
    if not isinstance(py_list, (list, tuple)):
        py_list = [py_list]
    for k in range(len(py_list)):
        py = py_list[k]
        logger_show('{}/{} running {} ...'.format(k+1, len(py_list), py),
                    logger)
        if not os.path.exists(py):
            logger_show('%s 不存在！'%py, None, level='warn')
            continue
        # cmd_str = 'python {}'.format(file)
        # os.system(cmd_str)
        # subprocess.call(cmd_str)
        p = subprocess.Popen(['python', py],
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              encoding='gbk'
                              )
        logger_show(p.communicate()[0], logger)
    # close_log_file(logger)


def rename_files_in_dir(dir_path, func_rename):
    '''
    对指定文件夹中的文件进行批量重命名
    
    Parameters
    ----------
    dir_path : str
        目标文件夹
    func_rename : function
        命名规则函数: name_new = func_rename(name)
    '''
    files = os.listdir(dir_path)
    for name in files:
        name_new = func_rename(name)
        old_path = os.path.join(dir_path, name)
        new_path = os.path.join(dir_path, name_new)
        os.rename(old_path, new_path)
        
        
def find_files_include_str(target_str, fpaths, re_match=False,
                           return_all_find=False, logger=None):
    '''    
    在指定文件路径列表中，查找哪些文件里面包含了目标字符串

    Parameters
    ----------
    target_str : str
        目标字符串
    fpaths : str, list
        文件路径列表
    re_match : bool
        若为True，则目标字符串 ``target_str`` 按正则表达式处理
    return_all_find : bool
        若为True，则返回所有找到的目标字符串，否则只返回第一个
    logger : None, logging.Logger
        日志记录器


    :returns: `dict` - 返回dict, key为找到的文件路径，value为包含目标字符串的文本内容(仅第一次出现的位置)
    '''
    def _isin(line, tgt):
        if not re_match:
            return tgt in line
        else:
            return not re.search(tgt, line) is None
    fpaths = check_list_arg(fpaths)
    files = []
    for fpath in fpaths:
        lines = read_lines(fpath, logger=logger)
        for line in lines:
            try:
                if _isin(line, target_str):
                    files.append([fpath, line])
                    if not return_all_find:
                        break
            except:
                if _isin(line, target_str.encode('gbk')):
                    files.append([fpath, line])
                    if not return_all_find:
                        break
    files = pd.DataFrame(files, columns=['fpath', 'content'])
    files = files.sort_values('fpath')
    return files


def find_dir_include_str(target_str, root_dir=None,
                         file_types=None, re_match=False,
                         return_all_find=False, logger=None,
                         **kwargs_getpath):
    '''    
    在指定目录下的文件中，查找哪些文件里面包含了目标字符串
    
    TODO
    ----
    增加排除文件类型设置

    Parameters
    ----------
    target_str : str
        目标字符串
    root_dir : str, None
        目标文件夹，目标字符串在此文件夹及其所有子文件内所有文本文件中搜索
        若为None，则在os.getcwd()下搜索
    file_types : None, str, list
        指定查找的文件后缀范围:

        - None, 在所有文件中查找
        - str, 指定一类文件后缀, 如'.py'表示在Python脚本中查找
        - list, 指定一个后缀列表, 如['.py', '.txt']
    re_match : bool
        若为True，则目标字符串 ``target_str`` 按正则表达式处理
    return_all_find : bool
        若为True，则返回所有找到的目标字符串，否则只返回第一个
    logger : None, logging.Logger
        日志记录器


    :returns: `dict` - 返回dict, key为找到的文件路径，value为包含目标字符串的文本内容(仅第一次出现的位置)
    '''
    if root_dir is None:
        root_dir = os.getcwd()
    fpaths = get_all_paths(root_dir, ext=file_types, **kwargs_getpath)
    files = find_files_include_str(target_str, fpaths,
                                   re_match=re_match,
                                   return_all_find=return_all_find,
                                   logger=logger)
    return files


def replace_str_in_file(fpath, ori_str, new_str,
                        fpath_new=None, kwargs_read={},
                        kwargs_write={}):
    '''
    | 替换文本文件fpath中的ori_str为new_str
    | fpath_new指定新文件路径
    | 若fpath_new为None，则新文件在原文件名加后缀_new
    | 若fpath_new为'replace'，则新文件替换原文件
    | 若fpath_new是函数，则新文件璐姐为fpath_new(fpath)
    | kwargs_read为read_lines函数接收参数
    | keargs_write为write_txt函数接收参数
    '''
    if isnull(fpath_new):
        ext = os.path.splitext(fpath)[-1]
        fpath_new_ = fpath.replace(ext, '_new'+ext)
    elif fpath_new == 'replace':
        fpath_new_ = fpath
    elif inspect.isfunction(fpath_new):
        fpath_new_ = fpath_new(fpath)
    else:
        fpath_new_ = fpath_new
    text = read_lines(fpath, split=False, **kwargs_read)
    text = text.replace(ori_str, new_str)
    write_txt([text], fpath_new_, **kwargs_write)
    
    
def replace_str_in_files(fpaths, ori_str, new_str,
                         fpath_new=None, kwargs_read={},
                         kwargs_write={}):
    '''文本文件内容批量替换，参数见 :func:`replace_str_in_file` '''
    for fpath in fpaths:
        replace_str_in_file(fpath, ori_str, new_str,
                            fpath_new=fpath_new,
                            kwargs_read=kwargs_read,
                            kwargs_write=kwargs_write)


def get_pip_pkgs_win_deprecated():
    '''获取windows下pip安装包列表'''
    def _is_version(x):
        '''判断是否为版本号'''
        x = x.split('.')
        if len(x) >= 2:
            try:
                if 0 <= int(x[0]) <= 99 and 0 <= int(x[1]) <= 99:
                    return True
            except:
                return False
        else:
            return False
    res = cmdrun('pip list', logger=False)
    res = res.split('\n')
    res = [re.sub(' +', ',', x.strip()) for x in res]
    df = []
    cols = ['pkg', 'version']
    for x in res:
        x = x.split(',')
        if len(x) != 2:
            continue
        if _is_version(x[-1]):
            df.append(x)
    df = pd.DataFrame(df, columns=cols)
    pkgs = df['pkg'].unique().tolist()
    return pkgs, df


def get_pip_pkgs_win():
    '''获取windows下pip安装包列表'''
    res = cmdrun('pip list', logger=False)
    res = res.split('\n')
    res = [x for x in res if len(re.findall(' +', x.strip())) == 1]
    res = res[2:]
    res = [re.sub(' +', '__,__', x.strip()) for x in res] # 替换连续空格
    res = [x.split('__,__') for x in res]
    df = pd.DataFrame(res, columns=['pkg', 'version'])
    pkgs = df['pkg'].unique().tolist()
    return pkgs, df


def _find_py_import_pkgs(py):
    '''
    | 查找py脚本中import的依赖包，返回列表
    | 可能并不完全准确
    '''
    lines = read_lines(py)
    lines = [x for x in lines if 'import ' in x]
    lines = [x.replace(',', ', ') for x in lines]
    lines = [x.replace('#', ' # ') for x in lines]
    lines = [re.sub(' +', ' ', x.strip()) for x in lines] # 替换连续空格
    res = []
    for line in lines:
        # 去除整行注释
        if line.startswith('#'):
            continue
        # from xxx(.) import yyy (as zzz)
        pkg = re.search(r'from .* import ', line)
        if not isnull(pkg):
            pkg = pkg.group().split(' ')[1]
            # 去除from .xxx 这种相对路径import
            if not pkg.startswith('.'):
                pkg = pkg.split('.')[0]
                res.append(pkg)
            continue
        # import xxx(.) (as yyy)
        # import xxx(.) (as yyy), aaa(.) (as bbb)
        # 必须import开头
        if not line.startswith('import '):
            continue
        pkgs = line.replace('import ', '').split(', ')
        for pkg in pkgs:
            # 不可能出现import .xxx这种相对路径导入方式
            pkg = pkg.split(' as ')[0]
            pkg = pkg.split(' ')[0]
            pkg = pkg.split('.')[0]
            res.append(pkg)
    res = list(set(res))
    # 额外筛选
    res = [x for x in res if not ',' in x]
    res = [x for x in res if not '"' in x]
    res = [x for x in res if not "'" in x]
    res = [x for x in res if not '>' in x]
    res = [x for x in res if not '(' in x]
    res = [x for x in res if not ')' in x]
    return res


def _find_import_pkgs(fdir):
    '''
    查找被import的包（fdir下的py文件中所有import的包）
    
    Examples
    --------
    >>> pkgs, df = _find_import_pkgs('../../DramKit/')
    >>> pkgs1, df1 = _find_import_pkgs('../../FinFactory/')
    '''
    pys = find_dir_include_str('import ', root_dir=fdir,
                               file_types='.py', abspath=True)
    res = []
    df = []
    pys = pys['fpath'].unique().tolist()
    for py in pys:
        tmp = _find_py_import_pkgs(py)
        res += tmp
        df += [[x, py] for x in tmp]
    res = list(set(res))
    df = pd.DataFrame(df, columns=['pkg', 'fpath'])
    df.drop_duplicates(subset=['pkg'], inplace=True)
    res.sort()
    df.sort_values('pkg', ascending=True, inplace=True)
    return res, df


def _get_pkg_requirements(fdir):
    '''
    获取依赖包
    
    Note
    ----
    pip包名称与导入包名称不一致的会丢失，比如talib包名为TA-Lib，会丢失
    
    Examples
    --------
    >>> fdir = '../../DramKit/'
    >>> pkgs = _get_pkg_requirements(fdir)
    '''
    pkgs_pip, df_pip = get_pip_pkgs_win()
    pkgs, df = _find_import_pkgs(fdir)
    reqs = [x for x in pkgs if x in pkgs_pip]
    reqs.sort()
    reqs_version = df_pip[df_pip['pkg'].isin(reqs)].copy()
    reqs_version.sort_values('pkg', ascending=True, inplace=True)
    reqs_str = '\n'.join(reqs)
    reqs_version_str = '\n'.join(['=='.join(x) for x in reqs_version.values])
    return (reqs, reqs_version), (reqs_str, reqs_version_str), (pkgs, df)


def get_filename(fpath, with_ext=True):
    '''获取文件名（去除前缀路径），with_ext为False则返回不带后缀'''
    if with_ext:
        return os.path.basename(fpath)
    else:
        return os.path.basename(os.path.splitext(fpath)[0])


def get_file_ext_type(fpath):
    '''提取文件扩展名'''
    return os.path.splitext(fpath)[-1]


def get_parent_path(path, n=1):
    '''获取路径path的n级父路径'''
    f = Path(path)
    res = eval('f'+'.parent'*n)
    return str(res).replace('\\', '/') + '/'


if __name__ == '__main__':
    fpath = './_test/load_text_test_utf8.csv'
    data1 = load_text(fpath, encoding='gbk')
    data2 = load_csv(fpath, encoding='gbk')
