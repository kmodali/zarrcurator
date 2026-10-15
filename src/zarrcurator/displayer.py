"""
This module contains the declaration and definition of the class Displayer.
"""

#Standard modules
import os
import sys
import matplotlib.pyplot as plt
import numpy as np
from textwrap import wrap

#Local modules
try:
    from .config import configObj
except:
    print( sys.exc_info() )
    print( f"Module 'config' import error in {__file__}" )


# Displayer
class Displayer:
    """ Class to create plots for the groups created using the distributorObj and diagnoserObj.
    """

    def __init__(self, diagObj, fileName, title, subTitles):
        
        self.diagnoserObj = diagObj
        """object[class Diagnoser]: Diagnoser Object.
        The zarrcurator creates an object of class Diagnoser to handle the task of diagnosing the input zarr stores.
        """
        
        self.fileName = fileName
        """str: A prefix string for the plot files that will be created.
        The plot files created by the displayer will be named with this prefix. 
        """
        
        self.title = title
        """str: Title text for the plots.
        The plot files created by the displayer will be have the title as specified in this variable. 
        """
        
        self.subTitles = subTitles
        """str: Title text for the sub-plots.
        The plot files created by the displayer will be have sub-plots and their titles are as specified in this variable. 
        """
        
        self.plotCount = 1
        """int: Count of the plots created.
        The plot files created by the displayer will be have names suffixed with this count. 
        """

    
    def make_autopct(values):
        def my_autopct(pct):
            total = sum(values)
            val = int(round(pct*total/100.0))
            return '{p:.2f}%'.format(p=pct)
        return my_autopct
    
    
    def createPiePlotsForSubGroups(self):
        """Create Pie chart plots for the subgroups.

        For creating pie chart plots for the subgroups based on the sub group distribution method.

        Args:
                None.
        Returns:
                None.
        """

        """
        input_all_labels_sorted, input_all_sizes_sorted, \
        all_labels_subGroups, inner_sizes, outer_sizes,  \
        titleText, subTitles, fileName
        """
        
        
        # Extract the list of variables and their sizes from the sorted list of tuples

        input_all_labels_sorted =  [ k[0].split('/')[-2] for k in self.diagnoserObj.sorted_tuplelist_obj ]
        print(input_all_labels_sorted)
        input_all_sizes_sorted = [ k[1] for k in self.diagnoserObj.sorted_tuplelist_obj ]
        print(input_all_sizes_sorted)

        all_labels_subGroups =  self.distributorObj.all_labels
        inner_sizes = self.distributorObj.all_sizes
        outer_sizes = self.distributorObj.sizes_subGroups

        size = 0.3
        
        fig, ax = plt.subplots( 2, 1, layout="constrained" )
                               #,gridspec_kw={'hspace': 0.5, 'wspace': 0.1})
        
        print( f'PLOT-1:\n {input_all_sizes_sorted} , {input_all_labels_sorted}' )
        ax[0].pie( input_all_sizes_sorted, 
                   labels=list(range(1,len(input_all_labels_sorted)+1,1)),
                   radius = 1.5, rotatelabels=True, textprops={'fontsize': 6} )
        ax[0].set_title( "\n".join(wrap(self.subTitles[0])), y=0, pad = -25, 
                         fontsize="xx-small" )
    
        ax[1].pie( input_all_sizes_sorted, labels=None, radius = 1,
                   rotatelabels=True,textprops={'fontsize': 1} )
        ax[1].legend( loc='center',\
                    ncol = 4, fontsize = 'xx-large', \
                    labels=['%1d %s, %1.1f' % (i, l[0], l[1] ) \
                    for i, l in zip(range(1,len(input_all_labels_sorted)+1,1),\
                        zip( input_all_labels_sorted, input_all_sizes_sorted ) ) ],\
                    prop={'size': 4} ) 
        ax[1].axis('off')
        
        fig.suptitle( "\n".join(wrap(self.title)), fontsize="x-large" )
        fig.tight_layout()
        fig.savefig( f"1_{self.fileName}",transparent=True, bbox_inches="tight" )
        fig.clear()
        plt.close()
        
        
        fig, ax = plt.subplots( 1, 1, layout="constrained" )
        inner_labels_groups=map(str,inner_sizes)
        print(inner_labels_groups)
        new_inner_labels=list(inner_labels_groups)
        print(new_inner_labels)
        
        print(f'PLOT-2:\n {inner_sizes} , {new_inner_labels}')
        ax.pie(inner_sizes, labels=all_labels_subGroups,
                rotatelabels=True,textprops={'fontsize': 6})
        ax.set_title("\n".join(wrap(self.subTitles[2])), y=0, pad = -25, \
                          fontsize="xx-small")
        
        fig.tight_layout()
        fig.subplot.left  = 0.1
        fig.savefig(f"2_{self.fileName}",transparent=True, bbox_inches="tight")
        fig.clear()
        plt.close()
        
        
        print(f'PLOT-3:\n {inner_sizes} , {all_labels_subGroups}')
        fig, ax = plt.subplots( 1, 1, layout="constrained" )
        
        ax.pie(inner_sizes, labels=new_inner_labels, \
                radius=1,  textprops={'fontsize': 6},rotatelabels=True, \
                wedgeprops=dict(width=size, edgecolor='w'))
        ax.set_title("\n".join(wrap(self.subTitles[1])), y=0, pad = -25, \
                          fontsize="xx-small")
    
        fig.suptitle("\n".join(wrap(self.title)), fontsize="x-large")
        fig.tight_layout()
        fig.subplot.left  = 0.1
        fig.savefig(f"3_{self.fileName}",transparent=True,bbox_inches="tight")
        fig.clear()
        plt.close()
        
    
        outer_labels_groups=map(str,outer_sizes)
        print(outer_labels_groups)
    
        new_outer_labels=list(outer_labels_groups)
        print(new_outer_labels)
    
        print(f'PLOT-4:\n {outer_sizes} , {new_outer_labels}')
        fig, ax = plt.subplots( 1, 1, layout="constrained" )
        
        ax.pie(outer_sizes, labels=new_outer_labels,radius=1,
               wedgeprops=dict(width=size, edgecolor='w'),
               textprops={'fontsize': 6},rotatelabels=True)
    
        ax.set_title("\n".join(wrap(self.subTitles[3])), y=0, pad = -25, \
                          fontsize="xx-small")
        
        fig.suptitle("\n".join(wrap(self.title)), fontsize="x-large")
        fig.savefig(f"4_{self.fileName}")
        fig.clear()
        plt.close()
        return


    def createHBarPlotsForExp(self, fileCount =  False, byteBins = False):
        """Create horizontal bar plots for the subgroups.

        For creating horizontal bar plots for the entire zarr stores in an experiment. The plots can be based on file count or file sizes.

        Args:
                bool:Flag to indicate if the count of the files is represented on the axis.
                bool:Flag to indicate if the sizes of the files is represented on the axis.
        Returns:
                None.
        """
        
        width=0.4
        ind = 0
        yLabels = [k.split('/')[-1] for k in self.diagnoserObj.exp_size_dict.keys()]

        print(f"{yLabels} {len(yLabels)})",flush=True)
        for k in self.diagnoserObj.exp_size_dict.keys():
            print(f"{k}",flush=True)
            print(f"{self.diagnoserObj.exp_size_dict[k]['count']}", flush=True)     
            print(f"{self.diagnoserObj.exp_size_dict[k]['size']}",flush=True)
        

        xValuesCount = [self.diagnoserObj.exp_size_dict[k]['count'] for k in self.diagnoserObj.exp_size_dict.keys()]
        xValuesSize = [self.diagnoserObj.exp_size_dict[k]['size'] / (1024 * 1024 * 1024 * 1024)  for k in self.diagnoserObj.exp_size_dict.keys()]

        
        ind  = np.arange(len(yLabels))
        
        if byteBins:
            xValuesGB = []
            yLabelsGB = []
            xValuesTB = []
            yLabelsTB = []
        
            for yLab,xVal in zip(yLabels,xValuesSize):
                if xVal < 1 :
                    xValuesGB.append(xVal)
                    yLabelsGB.append(yLab)
                else:
                    xValuesTB.append(xVal)
                    yLabelsTB.append(yLab)
        
            indTB  = np.arange(len(yLabelsTB))
            indGB  = np.arange(len(yLabelsGB))
        
            fig, ax = plt.subplots(nrows=1, ncols=2)
                    
            ax[0].barh( indTB + width, xValuesTB, width, color='orange', align='center') #label='Disk size'
            ax[0].set(yticks= indTB + width, yticklabels=yLabelsTB, ylim=[2*width - 1, len(yLabelsTB)])
            ax[0].set_xscale('log')
            ax[0].set_xlabel('Size in Tbytes')
            ax[0].set_ylabel('Zarr stores for each frequency and healpix level')
            if fileCount:
                ax[0].set_xlabel('#File count')
    
            print([ xVal*1000 for xVal in xValuesGB ])
            ax[1].barh( indGB + width,[ xVal*1000 for xVal in xValuesGB ], width, color='orange', align='center') #label='Disk size'
            ax[1].set(yticks= indGB + width, yticklabels=yLabelsGB, ylim=[2*width - 1, len(yLabelsGB)])
            ax[1].set_xscale('log')
            ax[1].set_xlim([0.01,1000])
            ax[1].set_xlabel('Size in Gbytes')
            ax[1].set_ylabel('Zarr stores for each frequency and healpix level')
            if fileCount:
                ax[1].set_xlabel('#File count')

            fig.tight_layout()

        else:
            fig = plt.figure(figsize=(10, 10))
            ax = fig.add_axes((0.1,0.2,0.8,0.6)) # create an Axes with some room below
            ax.tick_params(axis='y', pad=10)
            
            ax.barh( ind + width, xValuesSize, width, color='orange', align='center') #label='Disk size'
            ax.set(yticks= ind + width, yticklabels=yLabels, ylim=[2*width - 1, len(yLabels)])

            if fileCount:
                ax.set_xscale('log')
                ax.set_xlabel(r"Sizes in Tbytes")

                # create second Axes. Note the 0.0 height
                ax2 = fig.add_axes((0.1,0.1,0.8,0.0))
                ax2.yaxis.set_visible(False) # hide the yaxis
                
                #size_by_count = [xVal / 1000 for xVal in xValues]
                size_by_count = [xVal  for xVal in xValuesCount]
                ax2.plot(sorted(size_by_count),[0]*len(size_by_count))
                ax2.set_xscale('log')
                ax2.set_xlabel('#File count')
                ax.set_ylabel('Zarr stores for each frequency and healpix level')
            
            else:
                ax.set_xscale('log')
                ax.set_xlabel('Size in Tbytes')
                ax.set_ylabel('Zarr stores for each frequency and healpix level')
                
            # vertical line indicating the thresholds of 1GB, 200GB, 10TB & 24 TB 
            # representing the HSM system constraints
            ax.plot([0.001, 0.001], [0, len(yLabels)], "b--")#blue
            ax.plot([0.2, 0.2], [0, len(yLabels)], "r--")#red
            ax.plot([10, 10], [0, len(yLabels)], "k--")#black .. Tape size 
            
            ax.plot([24, 24], [0, len(yLabels)], "g--")#green

            plt.setp(ax.get_yticklabels(), rotation=30, horizontalalignment='right', fontsize='small')

        if not configObj.getBatchMode():
            plt.show()
        else:
            fileName =  os.path.join( configObj.getWorkingDir(), f"Figure_{self.plotCount}.png" )
            fig.savefig(fileName)
            fig.clear()
            self.plotCount += 1
        return


    def createHBarPlotForStoreVariables(self, zarrStore, fileCount =  False, byteBins = False):
        
        """Create horizontal bar plots for the sizes of the variables for a given zarr store.

        For creating horizontal bar plots for the entire variables in a zarr store. The plots can be based on file count or file sizes.

        Args:
                bool:Flag to indicate if the count of the files is represented on the axis.
                bool:Flag to indicate if the sizes of the files is represented on the axis.
        Returns:
                None.
        """

        varDict = {}
        varNames = []
        varSizes = []
        for k in self.diagnoserObj.exp_size_dict[zarrStore].keys():
            if k not in ['size','count']:
                var=k.split(os.path.sep)[-1]
                varDict[var] = {}
                if not fileCount:
                    varDict[var]['size'] = self.diagnoserObj.exp_size_dict[zarrStore][k]['size']
                else:
                    varDict[var]['size'] = self.diagnoserObj.exp_size_dict[zarrStore][k]['count']

        varDictNew=dict(sorted(varDict.items(), key=lambda item: item[1]['size'],reverse=True))
        varNames = list(varDictNew.keys())
        varSizes = [ item[1]['size'] for item in varDictNew.items()]
    
        fig, ax = plt.subplots(nrows=1, ncols=1,figsize=(8,16))
        width=0.4
        ind = 0
        indGB  = np.arange(len(varNames))
        
        ax.barh( indGB + width,varSizes, width, color='orange', align='center') #label='Disk size'
        ax.set(yticks= indGB + width, yticklabels=varNames, ylim=[2*width - 1, len(varNames)])
        plt.yticks(fontsize=9, rotation=30)
        ax.tick_params(axis='y', pad=2)
        ax.set_xscale('log')

        if not fileCount:
            # As of now hardcoded to change in future.
            ax.set_xticks([1e0,1e1,1e2,1e3,1e4,1e5,1e6,1e7,1e8,1e9,1e10,1e11,1e12,1e13])
            ax.set_xlim([1e2,1e13])
            ax.set_xlabel('Size in Bytes')
        else:
            ax.set_xticks([1,1e0,1e1,1e2,1e3,1e4,1e5,1e6])
            ax.set_xlim([1,1e6])
            ax.set_xlabel('File count')
        
        ax.set_ylabel('Variables')
        
        fig.tight_layout()

        if not configObj.getBatchMode():
            plt.show()
        else:
            fileName =  os.path.join( configObj.getWorkingDir(), f"{zarrStore.split('.')[0]}_Variables.png" )
            fig.savefig(fileName)
            fig.clear()


    def createHBarPlotForStoreTarTapes(self, zarrStoreTarTapeDict, tarCount =  False, tapeCount = False):
        
        """Create horizontal bar plots for the sizes of the variables for a given zarr store.

        For creating horizontal bar plots for the entire variables in a zarr store. The plots can be based on file count or file sizes.

        Args:
                bool:Flag to indicate if the count of the files is represented on the axis.
                bool:Flag to indicate if the sizes of the files is represented on the axis.
        Returns:
                None.
        """

        zarrNames = []
        tarCounts = []
        tapeCounts = []

        zarrNames = zarrStoreTarTapeDict.keys()
        
        for store in zarrNames:
            tarCounts.append( len( zarrStoreTarTapeDict[store]['tarBallList'] ) ) 
            tapeCounts.append( len( zarrStoreTarTapeDict[store]['tapeIDList'] ) )

        print( f"Count of tarballs: {tarCounts}" )
        print( f"Count of tapecounts: {tapeCounts}" )
        
        fig, ax = plt.subplots( nrows=1, ncols=1, figsize=(8,16) )
        width=0.4
        ind = 0
        indGB  = np.arange(len(zarrNames))
        
        varSizes = tarCounts
        if not tarCount:
            varSizes = tapeCounts
            
        ax.barh( indGB + width,varSizes, width, color='orange', align='center') #label='Disk size'
        ax.set(yticks= indGB + width, yticklabels=zarrNames, ylim=[2*width - 1, len(zarrNames)])
        plt.yticks(fontsize=9, rotation=30)
        ax.tick_params(axis='y', pad=2)
        ax.set_xscale('log')

        if not tarCount:
            # As of now hardcoded to change in future.
            ax.set_xlim([1,1e3])
            ax.set_xlabel('count of Tapes')
        else:
            ax.set_xlim([1,1e3])
            ax.set_xlabel('count of Tarballs')
        
        ax.set_ylabel('Zarr stores')
        
        fig.tight_layout()

        if not configObj.getBatchMode():
            plt.show()
        else:
            fileName =  os.path.join( configObj.getWorkingDir(), f"Zarrstore_TarTapeCounts.png" )
            fig.savefig( fileName )
            fig.clear()
