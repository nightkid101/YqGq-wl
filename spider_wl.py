from web_crawler_wl.YangqiGuoqi import *
from web_crawler_wl.Caizhengju import *

#配置logging
logger = logging.getLogger('爬取数据')
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
ch = logging.StreamHandler()
# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)

if __name__ == "__main__":

    # ###|--***央企部分***--|###
    #
    # # 1.国家能源投资集团有限责任公司
    # logger.info('开始爬取国家能源投资集团有限责任公司')
    # for keyWord in config.keywords_list:
    #     logger.info('开始爬取招标采购信息' + '关键词：' + keyWord)
    #     delUrlofGuoNengTou('http://www.dlzb.com/zb/search.php?kw=', keyWord)
    # for keyWord in config.keywords_list:
    #     logger.info('开始爬取中标公示' + '关键词：' + keyWord)
    #     delUrlofGuoNengTou('http://www.dlzb.com/zhongbiao/search.php?kw=', keyWord)
    #
    # # 2.中国兵器工业集团有限公司
    # for keyWord in config.keywords_list:
    #     logger.info('开始爬取中国兵器工业集团有限公司' + '关键词：' + keyWord)
    #     dealURLofBingQi(
    #         'http://www.norincogroup.com.cn/jsearch/search.do?appid=1&ck=x&imageField=&od=0&pagemode=result&pos=title%2Ccontent&q=',
    #         keyWord)
    #
    # # 3.中国国新控股有限责任公司
    # dealURLofGuoXinKongGu()
    #
    # # 4.中国铁路物资集团有限公司
    # dealURLofTieLuWuZi()
    #
    # # 5.中国西电集团有限公司
    # delURLofXiDian()
    #
    # # 6.南光（集团）有限公司[中国南光集团有限公司]
    # delURLofNanGuang()
    #
    # # 7.华侨城集团有限公司
    # delURLofHuaQiaoCheng()
    #
    # # 8.武汉邮电科学研究院有限公司
    # delURLofWuHanYouDian()
    #
    # # 9.上海诺基亚贝尔股份有限公司
    # delURLofNokiasbell()
    #
    # # 10.中国华录集团有限公司
    # delURLofHuaLu()
    #
    # # 11.中国广核集团有限公司
    # delURLofCGN()
    #
    # # 12.中国黄金集团有限公司
    # delURLofChinaGold()
    #
    # # 13.中国能源建设集团有限公司
    # delURLofceec()
    #
    # # 14.中国电力建设集团有限公司
    # delURLofPowerChina()
    #
    # # 15.中国航空器材集团有限公司
    # delURLofHangkongQicai()
    #
    # # 16.中国航空油料集团有限公司
    # delURLofHKYouliao()
    #
    # # 17.中国民航信息集团有限公司
    # delURLofMinHangXinXi()
    #
    # # 18.新兴际华集团有限公司
    # delURLofXinxingJihua()
    #
    # # 19.中国煤炭地质总局
    # delURLofMeitanZongju()
    #
    # # 20.中国冶金地质总局
    # delURLofYejinZongju()
    #
    # # 21.中国建设科技有限公司
    # delURLofJiansheKeji()
    #
    # # 22.中国保利集团有限公司
    # defURLofBaoli()
    #
    # # 23.中国医药集团有限公司
    # delURLofYiyaoJituan()
    #
    # # 24.中国林业集团有限公司
    # delURLofLinyeJituan()
    #
    # # 25.中国中丝集团有限公司
    # delURLofChinasilk()
    #
    # # 26.中国农业发展集团有限公司
    # delURLofNongyeFazhan()
    #
    # # 27.电信科学技术研究院有限公司
    # delURLofDTDianxin()
    #
    # # 28.中国普天信息产业集团有限公司
    # delURLofPutian()
    #
    # # 29.中国交通建设集团有限公司
    # delURLofJiaotongJianshe()
    #
    # # 30.中国铁道建筑有限公司
    # delURLofZhongguoTiejian()
    #
    # # 31.中国铁路工程集团有限公司
    # delURLofTieluGongcheng()
    #
    # # 32.中国铁路通信信号集团有限公司
    # delURLofTieluXinhao()
    #
    # # 33.中国中车集团有限公司
    # delURLofZhongche()
    #
    # # 34.中国建筑科学研究院有限公司
    # delURLofJianzhuKexueyuan()
    #
    # # 35.中国国际技术智力合作有限公司
    # delURLofJishuZhili()
    #
    # # 36.北京矿冶科技集团有限公司
    # delURLofBJKuangyeKeji()
    #
    # # 37.有研科技集团有限公司
    # delURLofYouyanKeji()
    #
    # # 38.中国有色矿业集团有限公司
    # delURLofYouseKuangye()
    #
    # # 39.中国建材集团有限公司
    # delURLofJiancaiJituan()
    #
    # # 40.中国盐业有限公司
    # delURLofZhongguoYanye()
    #
    # # 41.中国化学工程集团有限公司
    # delURLofHuaxueGongcheng()
    #
    # ###|--***财政局部分***--|###
    # # 1.河北省石家庄市财政局
    # HBShijiazhuangCaizhengju()
    #
    # # 2.河北省张家口市财政局
    # HBZhangjiakouCaizhengju()
    #
    # # 3.山西省太原市财政局
    # SXTaiyuanCZJ()
    #
    # # 4.山西省朔州市财政局
    # SXShuozhouCZJ()
    #
    # # 5.山西省沂州市财政局
    # SXYizhouCZJ()
    #
    # # 6.山西省晋中市财政局
    # SXJinzhongCZJ()
    #
    # # 7.山西省长治市财政局
    # SXChangzhiCZJ()
    #
    # # 8.山西省运城市财政局
    # SXYunchengCZJ()
    #
    # # 9.内蒙古包头市财政局
    # NMBaotouCZJ()
    #
    # # 10.辽宁省沈阳市财政局
    # LNShenyangCZJ()
    #
    # # 11.辽宁省大连市财政局
    # LNDaLianCZJ()
    #
    # # 12.辽宁省营口市财政局
    # LNYingkouCZJ()
    #
    # # 13.黑龙江省哈尔滨市财政局
    # HLJHaerbinCZJ()
    #
    # # 14.黑龙江省伊春市财政局
    # HLJYichuanCZJ()
    #
    # # 15.吉林省长春市财政局
    # JLChangchunCZJ()
    #
    # # 16.吉林省吉林市财政局
    # JLJilinCZJ()
    #
    # # 17.吉林省四平市财政局
    # JLSipingCZJ()
    #
    # # 18.吉林省白山市财政局
    # JLBaishanCZJ()
    #
    # # 19.上海市普陀区财政局
    # SHPutuoquCZJ()
    #
    # # 20.上海市静安区财政局
    # SHJinganCZJ()
    #
    # # 21.江苏省南京市财政局
    # JSNanjingCZJ()
    #
    # # 22.江苏省无锡市财政局
    # JSYixingCZJ()
    #
    # # 23.江苏省苏州市财政局
    # JSSuzhouCZJ()
    #
    # # 24.江苏省连云港财政局
    # JSLianyungangCZJ()
    #
    # # 25.江苏省淮安市财政局
    # JSHuaianCZJ()
    #
    # # 26.江苏省盐城市财政局
    # JSYanchengCZJ()
    #
    # # 27.江苏省宿迁市财政局
    # JSSuqianCZJ()
    #
    # # 28.浙江省杭州市财政局
    # ZJHangzhouCZJ()
    #
    # # 29.浙江省宁波市财政局
    # ZJNingboCZJ()
    #
    # # 30.浙江省温州市财政局
    # ZJWenzhouCZJ()
    #
    # # 31.浙江省湖州市财政局
    # ZJHuzhouCZJ()
    #
    # # 32.浙江省台州市财政局
    # ZJTaizhouCZJ()
    #
    # # 33.安徽省合肥市财政厅
    # AHHefeiCZJ()
    #
    # # 34.安徽省淮北市财政厅
    # AHHuaibeiCZJ()
    #
    # # 35.安徽省毫州市财政厅
    # AHBozhouCZJ()
    #
    # # 36.安徽省宿州市财政厅
    # AHSuzhouCZJ()
    #
    # # 37.安徽省蚌埠市财政厅
    # AHBengbuCZJ()
    #
    # # 38.安徽省阜阳市财政厅
    # AHFuyangCZJ()
    #
    # # 39.安徽省淮南市财政厅
    # AHHuainanCZJ()

    # 40.安徽省马鞍山市财政厅
    AHMaanshanCZJ()
