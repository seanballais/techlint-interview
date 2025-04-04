import * as React from 'react';
import {useRef, useState} from "react";
import {
    MAX_NUM_ITEMS_PER_PAGE,
    FailedJSONResponse,
    fetchIPAddressData,
    updateIPAddressData,
    IP, IPAddressData, IPAddressDataJSONResponse
} from "../../utils/api.ts";
import IPAddressDataState from './IPAddressDataState.tsx';
import {IPAddressTableProps} from "./props.ts";
import {clearTokens} from "../../utils/tokens.ts";
import {
    FormInputMessage,
    FormInputMessageType
} from "../FormInputMessage/FormInputMessage.tsx";

interface TableState {
    isLoadingData: boolean;
    areButtonsEnabled: boolean
}

function IPAddressTable({
                            ipAddressTableState,
                            setIPAddressTableState
                        }: IPAddressTableProps): React.ReactNode {
    const tableRef = useRef<HTMLDivElement>(null);

    const numPages: number = Math.ceil((ipAddressTableState.numTotalItems ?? 0) / MAX_NUM_ITEMS_PER_PAGE);
    let [state, setState] = useState<TableState>({
        isLoadingData: false,
        areButtonsEnabled: true
    });

    function handlePreviousButtonClick(): void {
        if (isFirstPage()) {
            return;
        }

        getPage(ipAddressTableState.pageNumber - 1);
    }

    function handleNextButtonClick(): void {
        if (isLastPage()) {
            return;
        }

        getPage(ipAddressTableState.pageNumber + 1);
    }

    function isFirstPage(): boolean {
        return ipAddressTableState.pageNumber == 0;
    }

    function isLastPage(): boolean {
        return ipAddressTableState.pageNumber + 1 >= numPages;
    }

    function getPage(pageNumber: number) {
        tableRef.current?.scrollIntoView();

        setState((state: TableState): TableState => ({
            ...state,
            isLoadingData: true,
            areButtonsEnabled: false
        }));

        // Empty the events.
        setIPAddressTableState((state: IPAddressDataState): IPAddressDataState => ({
            ...state,
            ips: []
        }));

        fetchIPAddressData(MAX_NUM_ITEMS_PER_PAGE, pageNumber)
            .then(async (response: Response): Promise<IPAddressDataJSONResponse> => {
                if (response.ok) {
                    return await response.json();
                }

                const {detail}: FailedJSONResponse = await response.json();
                const errorCode: string = detail.errors[0].code;
                throw new Error(`Error code: ${errorCode}`);
            })
            .then((responseData: IPAddressDataJSONResponse): void => {
                const data: IPAddressData = responseData.data;
                setIPAddressTableState((state: IPAddressDataState): IPAddressDataState => ({
                    ...state,
                    numTotalItems: data.num_total_items,
                    numItemsInPage: data.count,
                    pageNumber: data.page_number,
                    ips: data.ips
                }));

                setState((state: TableState): TableState => ({
                    ...state,
                    isLoadingData: false,
                    areButtonsEnabled: true
                }));
            })
            .catch((): void => {
                // Tokens are already invalid, so we need to remove the tokens
                // in storage. We reload so that we are back in the login page.
                clearTokens();
                window.location.reload();
            });
    }

    return (
        <div
            className='ip-address-table-container max-width-initial'
            ref={tableRef}>
            <h1>IP Addresses</h1>
            <table>
                <thead>
                <tr>
                    <th scope='col'>IP Address</th>
                    <th scope='col'>Label</th>
                    <th scope='col'>Comment</th>
                    <th scope='col'>Added by</th>
                    <th scope='col'>Actions</th>
                </tr>
                </thead>
                <tbody>
                <IPAddressTableRows parentState={state}
                                    dataState={ipAddressTableState}/>
                </tbody>
            </table>
            <div className='row pagination-row'>
                <button
                    className={isFirstPage() ? 'previous-button invisible' : 'previous-button'}
                    disabled={!state.areButtonsEnabled}
                    onClick={handlePreviousButtonClick}>&larr; Previous
                </button>
                <div
                    className='page-number'>{ipAddressTableState.pageNumber + 1}/{numPages}</div>
                <button
                    className={isLastPage() ? 'next-button invisible' : 'next-button'}
                    disabled={!state.areButtonsEnabled}
                    onClick={handleNextButtonClick}>Next &rarr;</button>
            </div>
        </div>
    );
}

interface IPAddressTableRowsState {
    parentState: TableState;
    dataState: IPAddressDataState;
}

function IPAddressTableRows({
                                parentState,
                                dataState
                            }: IPAddressTableRowsState): React.ReactNode {
    if (dataState.ips.length === 0) {
        if (parentState.isLoadingData) {
            return (
                <tr className='text-align-center'>
                    <td colSpan={5}>Loading data...</td>
                </tr>
            );
        } else {
            return (
                <tr className='text-align-center'>
                    <td colSpan={5}>No IP address added.</td>
                </tr>
            );
        }
    }

    return (
        dataState.ips.map((ip: IP): React.ReactNode => (
            <IPAddressTableRow key={ip.id} id={ip.id} ipAddress={ip.ip_address}
                               label={ip.label} comment={ip.comment}
                               recorderUsername={ip.recorder.username}/>
        ))
    );
}

interface RowProps {
    id: number,
    ipAddress: string,
    label: string;
    comment: string;
    recorderUsername: string
}

enum RowMode {
    VIEWING,
    EDITING
}

interface RowState {
    ipAddress: string,
    label: string;
    comment: string;
    mode: RowMode;
    ipAddressErrorMessage?: string;
    labelErrorMessage?: string;
    isIPAddressInputEnabled: boolean;
    isLabelInputEnabled: boolean;
    isCommentInputEnabled: boolean;
    areButtonsEnabled: boolean;
}

function IPAddressTableRow({
                               id,
                               ipAddress,
                               label,
                               comment, recorderUsername
                           }: RowProps): React.ReactNode {
    const ipAddressInputRef = useRef<HTMLInputElement>(null);
    const labelInputRef = useRef<HTMLInputElement>(null);
    const commentInputRef = useRef<HTMLInputElement>(null);

    const [rowState, setRowState] = useState<RowState>({
        ipAddress: ipAddress,
        label: label,
        comment: comment,
        mode: RowMode.VIEWING,
        isIPAddressInputEnabled: true,
        isLabelInputEnabled: true,
        isCommentInputEnabled: true,
        areButtonsEnabled: true
    });

    async function handleUpdateIPAddress(): Promise<void> {
        setRowState((data: RowState): RowState => ({
            ...data,
            ipAddressErrorMessage: undefined,
            labelErrorMessage: undefined,
            isIPAddressInputEnabled: false,
            isLabelInputEnabled: false,
            isCommentInputEnabled: false,
            areButtonsEnabled: false
        }));

        let ipAddressValue: string;
        if (ipAddressInputRef.current) {
            ipAddressValue = ipAddressInputRef.current.value;
        } else {
            ipAddressValue = rowState.ipAddress;
        }

        let labelValue: string;
        if (labelInputRef.current) {
            labelValue = labelInputRef.current.value;
        } else {
            labelValue = rowState.label;
        }

        let commentValue: string;
        if (commentInputRef.current) {
            commentValue = commentInputRef.current.value;
        } else {
            commentValue = rowState.comment;
        }

        let ipAddressUpdateValue: string | null = null;
        if (ipAddressValue != rowState.ipAddress) {
            ipAddressUpdateValue = ipAddressValue;
        }

        let labelUpdateValue: string | null = null;
        if (labelValue != rowState.label) {
            labelUpdateValue = labelValue;
        }

        let commentUpdateValue: string | null = null;
        if (commentValue != rowState.comment) {
            commentUpdateValue = commentValue
        }

        const response: Response = await updateIPAddressData(id, ipAddressUpdateValue, labelUpdateValue, commentUpdateValue);
        if (response.ok) {
            setRowState((data: RowState): RowState => ({
                ...data,
                ipAddress: ipAddressValue,
                label: labelValue,
                comment: commentValue,
            }));
            switchRowMode();
        } else {
            const {detail}: FailedJSONResponse = await response.json();

            // We already know that there is one error that is returned.
            if (detail.errors[0].code === 'invalid_ip_address') {
                setRowState((data: RowState): RowState => ({
                    ...data,
                    ipAddressErrorMessage: 'Invalid IP address.'
                }));
            } else if (detail.errors[0].code === 'unavailable_label') {
                setRowState((data: RowState): RowState => ({
                    ...data,
                    labelErrorMessage: 'Label is already used.'
                }));
            }
        }

        setRowState((data: RowState): RowState => ({
            ...data,
            isIPAddressInputEnabled: true,
            isLabelInputEnabled: true,
            isCommentInputEnabled: true,
            areButtonsEnabled: true
        }));
    }

    function switchRowMode(): void {
        if (rowState.mode === RowMode.VIEWING) {
            setRowState((state: RowState): RowState => ({
                ...state,
                mode: RowMode.EDITING
            }));
        } else {
            setRowState((state: RowState): RowState => ({
                ...state,
                mode: RowMode.VIEWING
            }));
        }
    }

    return (
        <tr key={id}>
            {
                (rowState.mode === RowMode.VIEWING)
                    ? (
                        <>
                            <td>{rowState.ipAddress}</td>
                            <td>{rowState.label}</td>
                            <td>{rowState.comment}</td>
                            <th scope='row'>@{recorderUsername}</th>
                            <td>
                                <button onClick={switchRowMode}>Edit</button>
                            </td>
                        </>
                    ) : (
                        <>
                            <td>
                                <div className='form-group'>
                                    <input ref={ipAddressInputRef}
                                           type='text' placeholder='IP Address'
                                           name='ipAddress'
                                           defaultValue={rowState.ipAddress}
                                           disabled={!rowState.isIPAddressInputEnabled}/>
                                    <FormInputMessage targetInput='ipAddress'
                                                      type={FormInputMessageType.Error}
                                                      message={rowState.ipAddressErrorMessage}/>
                                </div>
                            </td>
                            <td>
                                <div className='form-group'>
                                    <input ref={labelInputRef}
                                           type='text' placeholder='Label'
                                           name='label'
                                           defaultValue={rowState.label}
                                           disabled={!rowState.isLabelInputEnabled}/>
                                    <FormInputMessage targetInput='label'
                                                      type={FormInputMessageType.Error}
                                                      message={rowState.labelErrorMessage}/>
                                </div>
                            </td>
                            <td>
                                <input ref={commentInputRef}
                                       type='text' placeholder='Comment'
                                       name='comment'
                                       defaultValue={rowState.comment}
                                       disabled={!rowState.isCommentInputEnabled}/>
                            </td>
                            <th scope='row'>@{recorderUsername}</th>
                            <td>
                                <button className='margin-right-1rem'
                                        disabled={!rowState.areButtonsEnabled}
                                        onClick={handleUpdateIPAddress}>Save
                                </button>
                                <button disabled={!rowState.areButtonsEnabled}
                                        onClick={switchRowMode}>Cancel
                                </button>
                            </td>
                        </>
                    )
            }
        </tr>
    );
}

export default IPAddressTable;
