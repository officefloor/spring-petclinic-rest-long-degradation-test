package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.node.ObjectNode;

/** customer-code: customerCode is now '<CITY3>-<LAST3>-<NNNN>' with a per-city
 * sequence. Two owners in the same city get consecutive NNNN. */
@Tag("cp09")
class Cp09Tests extends AcceptanceBase {

	@Test
	void coreCityPrefixedPerCitySequence() throws Exception {
		ObjectNode a = ownerNode();
		a.put("city", "Sydney");
		a.put("lastName", "alpha");
		ObjectNode b = ownerNode();
		b.put("city", "Sydney");
		b.put("lastName", "bravo");
		String ca = fetchOwner(createOwnerOk(a)).get("customerCode").asText();
		String cb = fetchOwner(createOwnerOk(b)).get("customerCode").asText();
		assertTrue(ca.startsWith("SYD-ALP-"), ca);
		assertTrue(cb.startsWith("SYD-BRA-"), cb);
		assertEquals(Integer.parseInt(ca.substring(8)) + 1, Integer.parseInt(cb.substring(8)));
	}
}
