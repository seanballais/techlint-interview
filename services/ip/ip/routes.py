from dataclasses import dataclass
from enum import Enum
import ipaddress
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func
from sqlalchemy.engine import TupleResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import BinaryExpression, or_
from sqlmodel import Session, select, not_, col

from . import models
from .encode import get_ip_address_dict
from .db import get_session
from .schema import (AddNewIPAddressData, DeleteIPAddressData,
                     UpdateIPAddressData)


class RouteErrorCode(Enum):
    INVALID_IP_ADDRESS: str = 'invalid_ip_address'
    UNAVAILABLE_LABEL: str = 'unavailable_label'
    NONEXISTENT_IP_ADDRESS: str = 'nonexistent_ip_address'


class IPAddressEventType(Enum):
    IP_ADDRESS_ADDED: str = 'ip_address_added'
    IP_ADDRESS_MODIFIED_IP: str = 'ip_address_modified_ip'
    IP_ADDRESS_MODIFIED_IP_LABEL: str = 'ip_address_modified_ip_label'
    IP_ADDRESS_MODIFIED_IP_COMMENT: str = 'ip_address_modified_ip_comment'
    IP_ADDRESS_MODIFIED_IP_LABEL_COMMENT: str = 'ip_address_modified_ip_label_comment'
    IP_ADDRESS_MODIFIED_LABEL: str = 'ip_address_modified_label'
    IP_ADDRESS_MODIFIED_LABEL_COMMENT: str = 'ip_address_modified_label_comment'
    IP_ADDRESS_MODIFIED_COMMENT: str = 'ip_address_modified_comment'
    IP_ADDRESS_DELETED: str = 'ip_address_deleted'
    NONE: str = 'none'  # To be used a default value only on creation of app


@dataclass
class IPAddressData:
    ip_address: Optional[str]
    label: Optional[str]
    comment: Optional[str]

    @staticmethod
    def create_empty():
        return IPAddressData(None, None, None)

    @staticmethod
    def from_model(model: models.IPAddress):
        return IPAddressData(ip_address=model.ip_address, label=model.label,
                             comment=model.comment)

    def to_dict(self):
        d: dict = {}
        if self.ip_address:
            d['ip_address'] = self.ip_address

        if self.label:
            d['label'] = self.label

        if self.comment:
            d['comment'] = self.comment

        return d


@dataclass
class IPAddressDataDiff:
    old_data: IPAddressData
    new_data: IPAddressData


router: APIRouter = APIRouter()


@router.post('/ips')
async def new_ip_address(data: AddNewIPAddressData,
                         session: Session = Depends(get_session)) -> dict:
    if not _is_ip_address_valid(data.ip_address):
        raise _get_error_details_exception(422,
                                           RouteErrorCode.INVALID_IP_ADDRESS)

    ip_address: models.IPAddress = models.IPAddress(ip_address=data.ip_address,
                                                    label=data.label,
                                                    comment=data.comment,
                                                    recorder_id=data.recorder_id)

    session.add(ip_address)
    try:
        session.commit()
    except IntegrityError:
        raise _get_error_details_exception(409,
                                           RouteErrorCode.UNAVAILABLE_LABEL)

    session.refresh(ip_address)

    ip_address_data: dict = {
        'ip': get_ip_address_dict(ip_address)
    }

    _log_event(ip_address, IPAddressEventType.IP_ADDRESS_ADDED,
               data.recorder_id, IPAddressData.create_empty(), session)

    return {
        'data': ip_address_data
    }


@router.patch('/ips/{ip_address_id}')
async def update_ip_address(ip_address_id: int, data: UpdateIPAddressData,
                            session: Session = Depends(get_session)) -> dict:
    ip_address: models.IPAddress = _get_ip_address_object(ip_address_id,
                                                          session)
    if ip_address is None:
        raise _get_error_details_exception(404,
                                           RouteErrorCode.NONEXISTENT_IP_ADDRESS)

    old_ip_address_data: IPAddressData = IPAddressData.from_model(ip_address)

    # Validate inputs first.
    ip_address_updated: bool = False
    label_updated: bool = False
    comment_updated: bool = False

    if data.ip_address:
        if _is_ip_address_valid(data.ip_address):
            ip_address.ip_address = data.ip_address
            ip_address_updated = True
        else:
            raise _get_error_details_exception(422,
                                               RouteErrorCode.INVALID_IP_ADDRESS)

    if data.label:
        ip_address.label = data.label
        label_updated = True

    # Catch cases where the comment is an empty string.
    if data.comment is not None:
        ip_address.comment = data.comment
        comment_updated = True

    if data.ip_address or data.label or data.comment is not None:
        session.add(ip_address)
        try:
            session.commit()
        except IntegrityError:
            # The only time we will likely get an IntegrityError is when we try to
            # update the label of an IP address with a label already used by
            # another IP address.
            raise _get_error_details_exception(409,
                                               RouteErrorCode.UNAVAILABLE_LABEL)

    session.refresh(ip_address)

    ip_address_data: dict = {
        'ip': get_ip_address_dict(ip_address)
    }

    event_type: IPAddressEventType = IPAddressEventType.NONE
    if ip_address_updated and not label_updated and not comment_updated:
        event_type = IPAddressEventType.IP_ADDRESS_MODIFIED_IP
    elif ip_address_updated and label_updated and not comment_updated:
        event_type = IPAddressEventType.IP_ADDRESS_MODIFIED_IP_LABEL
    elif ip_address_updated and not label_updated and comment_updated:
        event_type = IPAddressEventType.IP_ADDRESS_MODIFIED_IP_COMMENT
    elif ip_address_updated and label_updated and comment_updated:
        event_type = IPAddressEventType.IP_ADDRESS_MODIFIED_IP_LABEL_COMMENT
    elif not ip_address_updated and label_updated and not comment_updated:
        event_type = IPAddressEventType.IP_ADDRESS_MODIFIED_LABEL
    elif not ip_address_updated and label_updated and comment_updated:
        event_type = IPAddressEventType.IP_ADDRESS_MODIFIED_LABEL_COMMENT
    elif not ip_address_updated and not label_updated and comment_updated:
        event_type = IPAddressEventType.IP_ADDRESS_MODIFIED_COMMENT

    _log_event(ip_address, event_type, data.updater_id, old_ip_address_data,
               session)

    return {
        'data': ip_address_data
    }


@router.delete('/ips/{ip_address_id}')
async def delete_ip_address(ip_address_id: int, data: DeleteIPAddressData,
                            session: Session = Depends(get_session)) -> dict:
    ip_address: models.IPAddress = _get_ip_address_object(ip_address_id,
                                                          session)
    if ip_address is None:
        raise _get_error_details_exception(404,
                                           RouteErrorCode.NONEXISTENT_IP_ADDRESS)

    old_ip_address_data: IPAddressData = IPAddressData.from_model(ip_address)

    ip_address.is_deleted = True
    session.add(ip_address)
    session.commit()
    session.refresh(ip_address)

    _log_event(ip_address, IPAddressEventType.IP_ADDRESS_DELETED,
               data.deleter_id, old_ip_address_data, session)

    return {
        'data': {
            'success': True
        }
    }


@router.get('/ips')
async def get_ip_addresses(
        ip_ids: Annotated[list[int] | None, Query(alias='id')] = None,
        items_per_page: Annotated[int, Query(le=50)] = 10,
        page_number: Annotated[int, Query()] = 0,
        session: Session = Depends(get_session)) -> dict:
    if ip_ids:
        or_expressions: list[BinaryExpression] = list(
            map(lambda id_: models.IPAddress.id == id_, ip_ids)
        )
        statement: Select = (
            select(models.IPAddress)
            .where(not_(models.IPAddress.is_deleted))
            .where(or_(*or_expressions))
            .order_by(col(models.IPAddress.created_on).desc()))
    else:
        statement: Select = (
            select(models.IPAddress)
            .where(not_(models.IPAddress.is_deleted))
            .order_by(col(models.IPAddress.created_on).desc())
            .offset(page_number * items_per_page)
            .limit(items_per_page))

    # This line below is taken from the fastapi-pagination project:
    # - https://github.com/uriyyo/fastapi-pagination/blob/1b718ff7b0c9087f684c38386f0e54ef5a3eec29/fastapi_pagination/ext/sqlmodel.py
    num_items: int = session.scalar(
        select(func.count('*')).select_from(statement.subquery()))

    total_num_items: int = session.scalar(
        select(func.count(models.IPAddress.id))
        .where(not_(models.IPAddress.is_deleted)))

    ip_addresses: TupleResult[models.IPAddress] = session.exec(statement)
    data: dict = {
        'count': num_items,
        'num_total_items': total_num_items,
        'page_number': page_number,
        'ips': []
    }
    for ip in ip_addresses:
        data['ips'].append(get_ip_address_dict(ip))

    return {
        'data': data
    }


@router.get('/audit-log')
async def get_audit_log(items_per_page: Annotated[int, Query(le=50)] = 10,
                        page_number: Annotated[int, Query()] = 0,
                        session: Session = Depends(get_session)) -> dict:
    statement: Select = (
        select(models.IPAddressEvent)
        .order_by(
            col(models.IPAddressEvent.recorded_on).desc())
        .offset(page_number * items_per_page)
        .limit(items_per_page))

    # This line below is taken from the fastapi-pagination project:
    # - https://github.com/uriyyo/fastapi-pagination/blob/1b718ff7b0c9087f684c38386f0e54ef5a3eec29/fastapi_pagination/ext/sqlmodel.py
    num_items: int = session.scalar(
        select(func.count('*')).select_from(statement.subquery()))

    total_num_items: int = session.scalar(
        select(func.count(models.IPAddressEvent.id)))

    events: TupleResult[models.IPAddressEvent] = session.exec(statement)
    data: dict = {
        'count': num_items,
        'num_total_items': total_num_items,
        'page_number': page_number,
        'events': []
    }
    for event in events:
        data['events'].append({
            'id': event.id,
            'type': event.event_type.name,
            'recorded_on': event.recorded_on,
            'ip': get_ip_address_dict(event.ip_address),
            'trigger_user_id': event.trigger_user_id,
            'old_data': event.old_data,
            'new_data': event.new_data
        })

    return {
        'data': data
    }


def _get_ip_address_object(ip_address_id,
                           session: Session = None) -> models.IPAddress:
    if session is None:
        session = next(get_session())

    statement: Select = select(models.IPAddress).where(
        models.IPAddress.id == ip_address_id,
        not_(models.IPAddress.is_deleted))
    ip_address: models.IPAddress = session.exec(statement).first()

    return ip_address


def _is_ip_address_valid(ip_address: str) -> bool:
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        return False

    return True


def _log_event(ip_address: models.IPAddress,
               event_type: IPAddressEventType,
               trigger_user_id: Optional[int],
               old_ip_address_data: IPAddressData,
               session: Session = None):
    if session is None:
        session = next(get_session())

    statement: Select = select(models.IPAddressEventType).where(
        models.IPAddressEventType.name == event_type.value
    )
    event_type: models.IPAddressEventType = session.exec(statement).first()
    if event_type:
        # We can do audit logging!
        ip_address_diff: IPAddressDataDiff = _diff_ip_address_data(ip_address,
                                                                   old_ip_address_data)

        user_event: models.IPAddressEvent = models.IPAddressEvent(
            trigger_user_id=trigger_user_id,
            ip_address_id=ip_address.id,
            event_type_id=event_type.id,
            old_data=ip_address_diff.old_data.to_dict(),
            new_data=ip_address_diff.new_data.to_dict())

        session.add(user_event)
        session.commit()
    else:
        # TODO: Update this to using a logging package.
        print('IP address event types are missing in the database. '
              'Please run the create-db.py to generate them.')


def _diff_ip_address_data(new_data: models.IPAddress,
                          old_data: IPAddressData) -> IPAddressDataDiff:
    old_ip_data: IPAddressData = IPAddressData.create_empty()
    new_ip_data: IPAddressData = IPAddressData.create_empty()

    if old_data.ip_address != new_data.ip_address:
        old_ip_data.ip_address = old_data.ip_address
        new_ip_data.ip_address = new_data.ip_address

    if old_data.label != new_data.label:
        old_ip_data.label = old_data.label
        new_ip_data.label = new_data.label

    if old_data.comment != new_data.comment:
        old_ip_data.comment = old_data.comment
        new_ip_data.comment = new_data.comment

    return IPAddressDataDiff(old_ip_data, new_ip_data)


def _convert_ip_address_to_pod(ip_address: models.IPAddress) -> IPAddressData:
    return IPAddressData(ip_address.ip_address, ip_address.label,
                         ip_address.comment)


def _get_error_details_exception(status_code: int,
                                 error_code: RouteErrorCode) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            'errors': [
                {
                    'code': error_code.value
                }
            ]
        }
    )
