// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title EvidenceRegistry
/// @notice 文件哈希存证合约：链上仅保存 SHA-256 摘要、写入账户与区块时间戳。
/// @dev 同一摘要只允许写入一次，重复写入会回滚，保证每条存证唯一。
contract EvidenceRegistry {
    struct Evidence {
        address owner;
        uint256 timestamp;
        bool exists;
    }

    mapping(bytes32 => Evidence) private _evidence;

    /// @notice 当前链上存证总数，便于演示与统计
    uint256 public totalEvidence;

    event EvidenceStored(
        bytes32 indexed fileHash,
        address indexed owner,
        uint256 timestamp
    );

    error EmptyHash();
    error EvidenceAlreadyExists(bytes32 fileHash);

    /// @notice 写入文件摘要，msg.sender 为链上写入账户
    /// @param fileHash 文件 SHA-256 摘要的 bytes32 表示
    /// @return success 写入成功返回 true
    function storeEvidence(bytes32 fileHash) external returns (bool success) {
        if (fileHash == bytes32(0)) revert EmptyHash();
        if (_evidence[fileHash].exists) revert EvidenceAlreadyExists(fileHash);

        _evidence[fileHash] = Evidence({
            owner: msg.sender,
            timestamp: block.timestamp,
            exists: true
        });
        totalEvidence += 1;

        emit EvidenceStored(fileHash, msg.sender, block.timestamp);
        return true;
    }

    /// @notice 查询摘要对应的存证内容
    /// @param fileHash 文件 SHA-256 摘要
    /// @return exists 是否存在
    /// @return owner 链上写入账户
    /// @return timestamp 区块时间戳（秒）
    function getEvidence(bytes32 fileHash)
        external
        view
        returns (
            bool exists,
            address owner,
            uint256 timestamp
        )
    {
        Evidence memory item = _evidence[fileHash];
        return (item.exists, item.owner, item.timestamp);
    }

    /// @notice 仅判断摘要是否已存证
    function verifyEvidence(bytes32 fileHash) external view returns (bool) {
        return _evidence[fileHash].exists;
    }
}
