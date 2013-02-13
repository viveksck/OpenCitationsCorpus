#!/usr/bin/env python
# encoding: utf-8
"""
OpenCitationsImportLibrary.py

Created by Martyn Whitwell on 2013-02-08.
Based on arXiv MetaHarvester by Dr Heinrich Hartmann, related-work.net,  2012


"""

import sys, os, time
from datetime import date, datetime, timedelta
from oaipmh.client import Client
from oaipmh.metadata import MetadataRegistry, oai_dc_reader
import MetadataReaders
import Batch
import Config
import hashlib, md5

class OAIImporter:

    METADATA_FORMAT_OAI_DC = {"prefix": 'oai_dc', "reader": oai_dc_reader}
    METADATA_FORMAT_PMC_FM = {"prefix": 'pmc_fm', "reader": MetadataReaders.MetadataReaderPMC()}
    METADATA_FORMAT_PMC = {"prefix": 'pmc', "reader": MetadataReaders.MetadataReaderPMC()}

    #default to OAI Dublin Core metadata format if note specified
    def __init__(self, uri, from_date, until_date, delta_months = 1, metadata = METADATA_FORMAT_OAI_DC):
        self.uri = uri
        self.from_date = datetime.strptime(from_date,"%Y-%m-%d")
        self.until_date = datetime.strptime(until_date,"%Y-%m-%d")
        self.delta_months = delta_months
        self.metadata = metadata

    def run(self):
        print "Importing from: %s" % self.uri
        print "From date: %s" % self.from_date
        print "Until date: %s" % self.until_date
        print "Delta months: %s" % self.delta_months

        registry = MetadataRegistry()
        registry.registerReader(self.metadata["prefix"], self.metadata["reader"])

        client = Client(self.uri, registry)
        identity = client.identify()

        print "Repository: %s" % identity.repositoryName()
        print "Metadata formats: %s" % client.listMetadataFormats()

        # got to update granularity or we barf with: 
        # oaipmh.error.BadArgumentError: Max granularity is YYYY-MM-DD:2003-04-10T00:00:00Z
        client.updateGranularity()

        #ElasticSearch batcher
        batcher = Batch.Batch()
    

        start = time.time()
        for (current_date, next_date) in self.loop_months():
            print "current_date: %s, next_date: %s" % (current_date, next_date)

            # get identifiers
            identifiers = list(self.get_identifiers(client, current_date, next_date))
            self.print_identifiers(identifiers)
            
            # get records
            #try:
            records = list(self.get_records(client, current_date, next_date))
            for record in records:
                batcher.add(self.bibify_record(record))
            #except:
            #    print "failed receiving records!"
            #    continue
            #self.print_records(records, max_recs = 2)

        #record = self.get_record(client, 'oai:pubmedcentral.nih.gov:3081214')

        
        batcher.clear()


        print 'Total Time spent: %d seconds' % (time.time() - start)



    def loop_months(self):
        if self.delta_months == 0: return

        current_date = self.from_date
        while True:
            if self.delta_months > 0 and current_date >= self.until_date: break
            if self.delta_months < 0 and current_date <= self.until_date: break
    
            carry, new_month = divmod(current_date.month - 1 + self.delta_months, 12)
            new_month += 1
            next_date = current_date.replace(year=current_date.year + carry, month=new_month)
        
            if self.delta_months > 0 and next_date > self.until_date: next_date = self.until_date
            if self.delta_months < 0 and next_date < self.until_date: next_date = self.until_date

            if self.delta_months > 0: 
                yield current_date, next_date
            if self.delta_months < 0: 
                yield next_date, current_date

            current_date = next_date

    def get_identifiers(self, client, start_date, end_date):
        print '****** Getting identifiers ******'
        print 'from   : %s' % start_date.strftime('%Y-%m-%d')
        print 'until  : %s' % end_date.strftime('%Y-%m-%d')

        chunk_time = time.time()

        print 'client.listIdentifiers(from_=',start_date,'until=',end_date,'metadataPrefix=',self.metadata["prefix"],'))'
        identifiers = list(client.listIdentifiers(
                from_          = start_date,  # yes, it is from_ not from
                until          = end_date,
                metadataPrefix = self.metadata["prefix"]
                ))

        d_time = time.time() - chunk_time
        print 'received %d identifiers in %d seconds' % (len(identifiers), d_time )
        chunk_time = time.time()

        return identifiers


    def get_records(self, client, start_date, end_date):
        print '****** Getting records ******'
        print 'from   : %s' % start_date.strftime('%Y-%m-%d')
        print 'until  : %s' % end_date.strftime('%Y-%m-%d')

        chunk_time = time.time()

        print 'client.listRecords(from_=',start_date,'until=',end_date,'metadataPrefix=',self.metadata["prefix"],'))'
        records = list(client.listRecords(
                from_          = start_date,  # yes, it is from_ not from
                until          = end_date,
                metadataPrefix = self.metadata["prefix"]
                ))

        d_time = time.time() - chunk_time
        print 'recieved %d records in %d seconds' % (len(records), d_time )
        chunk_time = time.time()

        return records



    def get_record(self, client, oaipmh_identifier):
        return list(client.getRecord(
            identifier = oaipmh_identifier,
            metadataPrefix = self.metadata["prefix"]))


    def bibify_record(self, record):
        header, metadata, about = record
        bibjson = metadata.getMap()
        bibjson["oaipmh.identifier"] = header.identifier()
        bibjson["oaipmh.datestamp"] = header.datestamp().isoformat()
        bibjson["oaipmh.setSpec"] = header.setSpec()
        bibjson["oaipmh.isDeleted"] = header.isDeleted()

        bibjson['_id'] = hashlib.md5(header.identifier()).hexdigest() #Not sure about sense of MD5 hash
        bibjson["url"] = Config.bibjson_url + bibjson["_id"]
        bibjson['_collection'] = [Config.bibjson_creator + '_____' + Config.bibjson_collname]
        bibjson['_created'] = datetime.now().strftime("%Y-%m-%d %H%M"),
        bibjson['_created_by'] = Config.bibjson_creator
        if "identifier" not in bibjson:
            bibjson["identifier"] = []
        bibjson["identifier"].append({"type":"bibsoup", "id":bibjson["_id"],"url":bibjson["url"]})

        return bibjson
        








    def print_records(self, records, max_recs = 2):
        print '****** Printing data ******'
        # for large collections this breaks
        count = 1

        for record in records:
            header, metadata, about = record
            map = metadata.getMap()
            print '****** Current record count: %i' % count
            print 'Header identifier: %s' % header.identifier()
            print 'Header datestamp: %s' % header.datestamp()
            print 'Header setSpec: %s' % header.setSpec()
            print 'Header isDeleted: %s' % header.isDeleted()
            print "KEYS+VALUES"
            for key, value in map.items():
                print '  ', key, ':', value
            print ""
            if count > max_recs: break
            count += 1


    def print_record(self, record):
        header, metadata, about = record
        map = metadata.getMap()
        print 'Header identifier: %s' % header.identifier()
        print 'Header datestamp: %s' % header.datestamp()
        print 'Header setSpec: %s' % header.setSpec()
        print 'Header isDeleted: %s' % header.isDeleted()
        print "KEYS+VALUES"
        for key, value in map.items():
            print '  ', key, ':', value
        print ""


    def print_identifiers(self, identifiers, max_recs = 20):
        print '****** Printing identifiers ******'
        # for large collections this breaks
        count = 1

        for header in identifiers:
            print 'Header identifier: %s' % header.identifier()
            print 'Header datestamp: %s' % header.datestamp()
            print 'Header setSpec: %s' % header.setSpec()
            print 'Header isDeleted: %s' % header.isDeleted()



